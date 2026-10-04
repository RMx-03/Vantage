import logging

import httpx

from app.services.email.sender import EmailDeliveryError, EmailMessage

logger = logging.getLogger(__name__)

_ENDPOINT = "https://api.brevo.com/v3/smtp/email"


def _split_sender(configured: str) -> tuple[str, str]:
    """Split `Name <addr@example.com>` into its parts.

    EMAIL_FROM is configured in the usual RFC display form, but Brevo wants the
    name and address as separate fields.
    """
    if "<" in configured and configured.rstrip().endswith(">"):
        name, _, rest = configured.partition("<")
        return name.strip() or "Vantage", rest.rstrip(">").strip()
    return "Vantage", configured.strip()


class BrevoEmailSender:
    def __init__(
        self,
        *,
        api_key: str,
        sender: str,
        timeout_seconds: int = 10,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._sender_name, self._sender_email = _split_sender(sender)
        self._timeout = timeout_seconds
        self._transport = transport

    def send(self, message: EmailMessage) -> None:
        # Brevo's shape differs from most providers: a structured sender object,
        # recipients as objects rather than strings, and textContent/htmlContent
        # rather than text/html.
        payload: dict[str, object] = {
            "sender": {"name": self._sender_name, "email": self._sender_email},
            "to": [{"email": message.to}],
            "subject": message.subject,
            "textContent": message.text,
        }
        if message.html:
            payload["htmlContent"] = message.html

        try:
            with httpx.Client(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = client.post(
                    _ENDPOINT,
                    json=payload,
                    # Brevo authenticates with an `api-key` header, not Bearer.
                    headers={
                        "api-key": self._api_key,
                        "Content-Type": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            # Deliberately does not include the recipient or body.
            raise EmailDeliveryError(
                f"Email transport failed: {type(exc).__name__}"
            ) from exc

        if response.status_code == 429:
            # Brevo's free tier allows 300/day. This is the boundary being hit, and
            # it must be visible rather than swallowed.
            logger.error("email.rate_limited status=429 provider=brevo")
            raise EmailDeliveryError("Email provider rate limit reached.")

        # Brevo answers 201 Created on success, not 200.
        if response.status_code >= 400:
            logger.error(
                "email.rejected status=%s provider=brevo", response.status_code
            )
            raise EmailDeliveryError(
                f"Email provider rejected the message: HTTP {response.status_code}"
            )
