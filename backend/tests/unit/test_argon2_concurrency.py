"""Argon2 memory must stay bounded however many requests arrive at once.

Each hash needs 19 MiB. FastAPI runs sync endpoints on a 40-thread pool, so
without a cap a burst of logins or sign-ups can demand ~760 MiB on a 512 MB
dyno. Per-client rate limits do not prevent this: a caller reaching Heroku
directly can choose the forwarded address the limits key on.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.core.config import settings
from app.core.security import passwords


class _CountingHasher:
    """Stands in for argon2's hasher and records peak concurrency."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.active = 0
        self.peak = 0

    def _enter(self) -> None:
        with self._lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        time.sleep(0.05)
        with self._lock:
            self.active -= 1

    def hash(self, password: str) -> str:
        self._enter()
        return "$argon2id$fake"

    def verify(self, encoded: str, password: str) -> bool:
        self._enter()
        return True

    def check_needs_rehash(self, encoded: str) -> bool:
        return False


@pytest.fixture()
def counting(monkeypatch: pytest.MonkeyPatch) -> _CountingHasher:
    fake = _CountingHasher()
    monkeypatch.setattr(passwords, "_hasher", fake)
    monkeypatch.setattr(settings, "ARGON2_MAX_CONCURRENCY", 2)
    return fake


def test_concurrent_hashing_is_capped(counting: _CountingHasher) -> None:
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: passwords.hash_password("pw"), range(8)))
    assert counting.peak <= 2, f"{counting.peak} hashes ran at once"


def test_concurrent_verification_is_capped(counting: _CountingHasher) -> None:
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: passwords.verify_password("pw", "h"), range(8)))
    assert counting.peak <= 2, f"{counting.peak} verifications ran at once"


def test_timing_parity_verification_is_capped_too(counting: _CountingHasher) -> None:
    # The unknown-account path runs a dummy verify; it costs the same memory.
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: passwords.dummy_verify(), range(8)))
    assert counting.peak <= 2, f"{counting.peak} dummy verifications ran at once"
