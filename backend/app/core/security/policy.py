from functools import lru_cache
from pathlib import Path
import re
import unicodedata

from app.domain.auth import AUTH_WEAK_PASSWORD
from app.domain.errors import VantageError

MIN_PASSWORD_LENGTH = 12
# Bounds the work Argon2 will do. Without a ceiling, a multi-megabyte password
# is a cheap way to burn dyno CPU.
MAX_PASSWORD_LENGTH = 128
MAX_EMAIL_LENGTH = 254

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_COMMON_PASSWORDS_FILE = Path(__file__).with_name("common_passwords.txt")


def _weak(message: str) -> VantageError:
    return VantageError(code=AUTH_WEAK_PASSWORD, safe_message=message)


@lru_cache(maxsize=1)
def _common_passwords() -> frozenset[str]:
    text = _COMMON_PASSWORDS_FILE.read_text(encoding="utf-8", errors="ignore")
    return frozenset(line.strip().lower() for line in text.splitlines() if line.strip())


def normalize_email(raw: str) -> str:
    """Trim and lowercase an address, then validate its shape.

    Local-part dots are preserved. Stripping them would silently merge
    addresses that the mail provider may treat as distinct.
    """
    candidate = raw.strip().lower()
    if len(candidate) > MAX_EMAIL_LENGTH or not _EMAIL_PATTERN.match(candidate):
        raise VantageError(
            code=AUTH_WEAK_PASSWORD,
            safe_message="Enter a valid email address.",
        )
    return candidate


def normalize_password(password: str) -> str:
    """NFKC-normalize a password.

    Register hashes the normalized form, so every other path that touches a
    password must normalize identically or the same typed characters produce a
    different hash. Login diverging from this is why full-width and IME input
    could be registered and then never used again.
    """
    return unicodedata.normalize("NFKC", password)


def validate_password(password: str, *, email: str) -> str:
    """Return the NFKC-normalized password, or raise VantageError.

    Normalization happens before every length check and before hashing, so the
    same typed password always produces the same hash regardless of how the
    client's input method encoded it.
    """
    normalized = normalize_password(password)

    if len(normalized) < MIN_PASSWORD_LENGTH:
        raise _weak(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(normalized) > MAX_PASSWORD_LENGTH:
        raise _weak(f"Password must be at most {MAX_PASSWORD_LENGTH} characters.")
    if normalized.lower() in _common_passwords():
        raise _weak("That password is too common. Choose something less predictable.")

    local_part = email.split("@", 1)[0].strip().lower()
    if len(local_part) >= 3 and local_part in normalized.lower():
        raise _weak("Password must not contain your email address.")

    return normalized
