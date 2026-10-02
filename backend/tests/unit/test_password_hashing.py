import time

from app.core.security.passwords import (
    PASSWORD_ALGO,
    dummy_verify,
    hash_password,
    needs_rehash,
    verify_password,
)


def test_algo_identifier_is_argon2id() -> None:
    assert PASSWORD_ALGO == "argon2id"


def test_hash_is_not_the_plaintext() -> None:
    encoded = hash_password("correct horse battery staple")
    assert "correct horse" not in encoded
    assert encoded.startswith("$argon2id$")


def test_hash_is_salted_so_two_hashes_differ() -> None:
    a = hash_password("correct horse battery staple")
    b = hash_password("correct horse battery staple")
    assert a != b


def test_correct_password_verifies() -> None:
    encoded = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", encoded) is True


def test_wrong_password_does_not_verify() -> None:
    encoded = hash_password("correct horse battery staple")
    assert verify_password("wrong horse battery staple", encoded) is False


def test_malformed_hash_returns_false_rather_than_raising() -> None:
    # A corrupted stored hash must fail closed, not 500.
    assert verify_password("anything", "not-a-hash") is False


def test_current_parameters_do_not_need_rehash() -> None:
    assert needs_rehash(hash_password("correct horse battery staple")) is False


def test_uses_spec_parameters_tuned_for_a_512mb_dyno() -> None:
    encoded = hash_password("correct horse battery staple")
    # $argon2id$v=19$m=19456,t=2,p=1$...
    assert "m=19456,t=2,p=1" in encoded


def test_dummy_verify_costs_comparable_time_to_a_real_verify() -> None:
    # Timing parity is what stops login from leaking whether an account exists.
    encoded = hash_password("correct horse battery staple")

    start = time.perf_counter()
    verify_password("wrong horse battery staple", encoded)
    real = time.perf_counter() - start

    start = time.perf_counter()
    dummy_verify()
    dummy = time.perf_counter() - start

    assert dummy > real * 0.5
