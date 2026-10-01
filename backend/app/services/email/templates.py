"""Transactional message bodies.

Plain text only. It renders everywhere, cannot carry a tracking pixel, and
keeps these messages small — which matters on a 300-per-day free tier.
"""

from urllib.parse import quote

from app.core.config import settings
from app.services.email.sender import EmailMessage


def _base_url() -> str:
    return settings.APP_BASE_URL.rstrip("/")


def _lifetime(seconds: int) -> str:
    """Render a link lifetime the way the email states it.

    Derived from the same setting that expires the token, so the text can never
    promise longer than the link actually lives.
    """
    minutes = max(seconds // 60, 1)
    if minutes > 90 and minutes % 60 == 0:
        hours = minutes // 60
        return f"{hours} hour" if hours == 1 else f"{hours} hours"
    return f"{minutes} minute" if minutes == 1 else f"{minutes} minutes"


def verification_message(to: str, token: str) -> EmailMessage:
    link = f"{_base_url()}/verify-email?token={quote(token)}"
    return EmailMessage(
        to=to,
        subject="Confirm your Vantage address",
        text=(
            "Confirm this address to finish setting up your Vantage account.\n\n"
            f"{link}\n\n"
            f"This link works once and expires in {_lifetime(settings.EMAIL_VERIFICATION_TTL_SECONDS)}.\n\n"
            "If you did not create a Vantage account, no action is needed.\n"
        ),
    )


def password_reset_message(to: str, token: str) -> EmailMessage:
    link = f"{_base_url()}/reset-password?token={quote(token)}"
    return EmailMessage(
        to=to,
        subject="Reset your Vantage password",
        text=(
            "Use this link to choose a new Vantage password.\n\n"
            f"{link}\n\n"
            f"This link works once and expires in {_lifetime(settings.PASSWORD_RESET_TTL_SECONDS)}.\n\n"
            "If you did not request a reset, ignore this message. Your password "
            "has not changed.\n"
        ),
    )


def duplicate_registration_message(to: str) -> EmailMessage:
    """Sent when someone tries to register an address that already exists.

    This is what makes enumeration resistance honest: the registration form
    returns the same response either way, and the real account owner — not the
    person at the form — is the one told about it. It carries no link and no
    token, so it hands a guesser nothing.
    """
    return EmailMessage(
        to=to,
        subject="Someone tried to create a Vantage account with your address",
        text=(
            "Someone attempted to register a Vantage account using this address. "
            "An account already exists, so nothing was created or changed.\n\n"
            "If this was you, sign in as usual. If you have forgotten your "
            "password, use the password reset option on the sign-in page.\n\n"
            "If this was not you, no action is needed.\n"
        ),
    )
