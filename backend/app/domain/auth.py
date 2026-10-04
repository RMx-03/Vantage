"""Authentication error codes and shared auth DTOs.

Codes are part of the API contract: the frontend switches on them. There is
deliberately no AUTH_EMAIL_IN_USE — returning it would tell an attacker which
addresses are registered.
"""

AUTH_REQUIRED = "AUTH_REQUIRED"
AUTH_INVALID = "AUTH_INVALID"
AUTH_TOKEN_EXPIRED = "AUTH_TOKEN_EXPIRED"
AUTH_RATE_LIMITED = "AUTH_RATE_LIMITED"
AUTH_ACCOUNT_LOCKED = "AUTH_ACCOUNT_LOCKED"
AUTH_EMAIL_UNVERIFIED = "AUTH_EMAIL_UNVERIFIED"
AUTH_WEAK_PASSWORD = "AUTH_WEAK_PASSWORD"

INVALID_CREDENTIALS_MESSAGE = "Email or password is incorrect."
GENERIC_ACCEPTED_MESSAGE = "If that address can receive mail, a message is on its way."
