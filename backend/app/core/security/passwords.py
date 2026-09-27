"""Argon2id password hashing.

Parameters follow the OWASP Password Storage Cheat Sheet and are tuned for a
512 MB Heroku Basic dyno. argon2-cffi defaults to 64 MiB per hash, which under
concurrent logins on this plan risks memory exhaustion; 19 MiB is the OWASP
minimum and leaves headroom.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

PASSWORD_ALGO = "argon2id"

_MEMORY_COST_KIB = 19456
_TIME_COST = 2
_PARALLELISM = 1

_hasher = PasswordHasher(
    memory_cost=_MEMORY_COST_KIB,
    time_cost=_TIME_COST,
    parallelism=_PARALLELISM,
)

# A real hash of a value no account uses, verified against when the supplied
# email matches no user. It makes the unknown-account path cost the same as the
# wrong-password path, so response time does not reveal which one happened.
_DUMMY_HASH = _hasher.hash("vantage-dummy-password-for-timing-parity")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    """Return whether the password matches. Never raises.

    A stored hash that is corrupt or written by an unknown algorithm must fail
    closed rather than surface as a 500.
    """
    try:
        return _hasher.verify(encoded_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(encoded_hash: str) -> bool:
    """Whether this hash predates the current parameters."""
    try:
        return _hasher.check_needs_rehash(encoded_hash)
    except InvalidHashError:
        return True


def dummy_verify() -> None:
    """Burn the cost of one verification without checking anything."""
    try:
        _hasher.verify(_DUMMY_HASH, "not-the-dummy-password")
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        pass
