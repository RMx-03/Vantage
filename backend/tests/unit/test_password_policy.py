import pytest

from app.core.security.policy import normalize_email, validate_password
from app.domain.auth import AUTH_WEAK_PASSWORD
from app.domain.errors import VantageError


def test_email_is_trimmed_and_lowercased() -> None:
    assert normalize_email("  Operator@Vantage.Quant  ") == "operator@vantage.quant"


def test_email_local_part_dots_are_preserved() -> None:
    # Collapsing a.b@ and ab@ into one account is surprising behavior that
    # silently merges distinct addresses. We do not do it.
    assert normalize_email("a.b@example.com") == "a.b@example.com"


def test_email_rejects_missing_at_sign() -> None:
    with pytest.raises(VantageError):
        normalize_email("not-an-email")


def test_email_rejects_over_254_characters() -> None:
    with pytest.raises(VantageError):
        normalize_email("a" * 250 + "@example.com")


def test_password_below_minimum_length_is_rejected() -> None:
    with pytest.raises(VantageError) as excinfo:
        validate_password("short", email="user@example.com")
    assert excinfo.value.code == AUTH_WEAK_PASSWORD


def test_password_above_maximum_length_is_rejected() -> None:
    # Bounds Argon2 CPU cost: an unbounded password is a cheap DoS.
    with pytest.raises(VantageError):
        validate_password("a" * 129, email="user@example.com")


def test_common_password_is_rejected() -> None:
    with pytest.raises(VantageError):
        validate_password("password1234", email="user@example.com")


def test_password_containing_email_local_part_is_rejected() -> None:
    with pytest.raises(VantageError):
        validate_password("operator-strong-77", email="operator@example.com")


def test_no_composition_rules_are_enforced() -> None:
    # NIST SP 800-63B advises against mandated character classes. A long
    # all-lowercase passphrase is acceptable.
    assert validate_password("correct horse battery staple", email="u@example.com")


def test_password_is_nfkc_normalized() -> None:
    # U+FF21 FULLWIDTH LATIN CAPITAL A normalizes to "A".
    result = validate_password("Ａ" + "bcdefghijklm", email="u@example.com")
    assert result.startswith("A")
