from functools import lru_cache

from app.core.config import settings
from app.services.email.brevo import BrevoEmailSender
from app.services.email.noop import NoopEmailSender
from app.services.email.sender import EmailDeliveryError, EmailMessage, EmailSender
from app.services.email.smtp import SmtpEmailSender

__all__ = [
    "EmailDeliveryError",
    "EmailMessage",
    "EmailSender",
    "get_email_sender",
]


@lru_cache(maxsize=1)
def get_email_sender() -> EmailSender:
    """Select the configured sender.

    Defaults to the no-op sender. A misconfigured deployment therefore fails
    by not delivering mail, which is visible in logs, rather than by mailing
    real people from a test environment.
    """
    if settings.EMAIL_PROVIDER.strip().lower() == "brevo":
        if not settings.BREVO_API_KEY:
            raise RuntimeError("EMAIL_PROVIDER=brevo requires BREVO_API_KEY.")
        return BrevoEmailSender(
            api_key=settings.BREVO_API_KEY,
            sender=settings.EMAIL_FROM,
            timeout_seconds=settings.EMAIL_TIMEOUT_SECONDS,
        )
    if settings.EMAIL_PROVIDER.strip().lower() == "smtp":
        return SmtpEmailSender(
            host=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USERNAME,
            password=settings.SMTP_PASSWORD,
            sender=settings.EMAIL_FROM,
            timeout_seconds=settings.EMAIL_TIMEOUT_SECONDS,
        )
    return NoopEmailSender()
