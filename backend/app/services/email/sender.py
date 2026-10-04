"""Transactional email port.

The provider stays behind this protocol so the rest of the application never
imports an HTTP client, and so tests and local development can run a sender
that delivers nothing.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text: str
    html: str | None = None


class EmailDeliveryError(Exception):
    """Raised when a message could not be handed to the provider.

    The string form never contains the recipient address or message body; this
    exception ends up in logs.
    """


class EmailSender(Protocol):
    def send(self, message: EmailMessage) -> None: ...
