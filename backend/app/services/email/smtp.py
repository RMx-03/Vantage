import logging
import smtplib
import ssl
from collections.abc import Callable
from email.message import EmailMessage as MimeMessage
from typing import Any

from app.services.email.sender import EmailDeliveryError, EmailMessage

logger = logging.getLogger(__name__)

# Port 465 speaks TLS from the first byte; every other port starts in clear and
# must be upgraded with STARTTLS before the password is sent.
_IMPLICIT_TLS_PORT = 465

Connect = Callable[[str, int, int, bool], Any]


def _connect(host: str, port: int, timeout: int, implicit_tls: bool) -> Any:
    if implicit_tls:
        return smtplib.SMTP_SSL(
            host, port, timeout=timeout, context=ssl.create_default_context()
        )
    return smtplib.SMTP(host, port, timeout=timeout)


class SmtpEmailSender:
    """Delivers through any SMTP server; in practice Gmail with an app password.

    Gmail needs no domain of our own and signs the message as gmail.com, so it
    reaches inboxes where a third-party relay sending "as" a Gmail address
    would not. The address in EMAIL_FROM must be the authenticated account (or
    one of its verified aliases); Gmail rewrites any other From to the account.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        timeout_seconds: int = 10,
        connect: Connect | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._sender = sender
        self._timeout = timeout_seconds
        self._connect = connect or _connect

    def send(self, message: EmailMessage) -> None:
        mime = MimeMessage()
        mime["From"] = self._sender
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.text)
        if message.html:
            mime.add_alternative(message.html, subtype="html")

        implicit_tls = self._port == _IMPLICIT_TLS_PORT
        try:
            with self._connect(
                self._host, self._port, self._timeout, implicit_tls
            ) as smtp:
                if not implicit_tls:
                    # Raises if the server cannot upgrade, so the password is
                    # never sent in clear.
                    smtp.starttls(context=ssl.create_default_context())
                smtp.login(self._username, self._password)
                smtp.send_message(mime)
        except smtplib.SMTPAuthenticationError as exc:
            logger.error("email.auth_failed provider=smtp code=%s", exc.smtp_code)
            raise EmailDeliveryError("Email provider refused the credentials.") from exc
        except smtplib.SMTPResponseException as exc:
            # Gmail answers 550 once the daily sending limit is reached.
            logger.error("email.rejected provider=smtp code=%s", exc.smtp_code)
            raise EmailDeliveryError(
                f"Email provider rejected the message: SMTP {exc.smtp_code}"
            ) from exc
        except (smtplib.SMTPException, OSError) as exc:
            # Deliberately does not include the recipient, body or credential.
            raise EmailDeliveryError(
                f"Email transport failed: {type(exc).__name__}"
            ) from exc
