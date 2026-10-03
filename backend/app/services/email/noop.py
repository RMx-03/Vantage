import logging

from app.services.email.sender import EmailMessage

logger = logging.getLogger(__name__)


class NoopEmailSender:
    """Records that a message would have been sent, and sends nothing.

    The subject is logged because it identifies which flow ran. The body is
    never logged: it carries the verification or reset link, and a link in a
    log file is a usable credential.
    """

    def send(self, message: EmailMessage) -> None:
        logger.info(
            "email.suppressed subject=%r recipient_domain=%s",
            message.subject,
            message.to.rsplit("@", 1)[-1] if "@" in message.to else "unknown",
        )
