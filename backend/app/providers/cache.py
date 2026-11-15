"""Provider request cache: the protocol and an in-memory implementation.

The cache is not a source. It stores reduced payloads only, never a raw
provider document and never a key.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol

from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CacheEntry:
    payload: Any
    content_hash: str
    retrieved_at: datetime


def compute_content_hash(payload: Any) -> str:
    """SHA-256 of the payload's canonical JSON, stable across key order."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ProviderCache(Protocol):
    def get(
        self, provider: str, cache_key: str, valid_for_date: date
    ) -> CacheEntry | None: ...

    def put(
        self,
        provider: str,
        cache_key: str,
        valid_for_date: date,
        payload: Any,
        retrieved_at: datetime,
        *,
        immutable: bool = False,
    ) -> CacheEntry: ...


class InMemoryProviderCache:
    """Dict-backed cache for unit tests."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str, date], CacheEntry] = {}

    def get(
        self, provider: str, cache_key: str, valid_for_date: date
    ) -> CacheEntry | None:
        return self._entries.get((provider, cache_key, valid_for_date))

    def put(
        self,
        provider: str,
        cache_key: str,
        valid_for_date: date,
        payload: Any,
        retrieved_at: datetime,
        *,
        immutable: bool = False,
    ) -> CacheEntry:
        entry = CacheEntry(payload, compute_content_hash(payload), retrieved_at)
        self._entries[(provider, cache_key, valid_for_date)] = entry
        return entry


def cache_get_safely(
    cache: ProviderCache, provider: str, key: str, valid_for: date
) -> CacheEntry | None:
    """Cache read where a database failure is a miss, logged with a fixed line."""
    try:
        return cache.get(provider, key, valid_for)
    except SQLAlchemyError:
        logger.warning("provider_cache_unavailable")
        return None


def cache_put_safely(
    cache: ProviderCache,
    provider: str,
    key: str,
    valid_for: date,
    payload: Any,
    retrieved_at: datetime,
    *,
    immutable: bool = False,
) -> None:
    """Cache write where a database failure skips the write, logged the same way."""
    try:
        cache.put(provider, key, valid_for, payload, retrieved_at, immutable=immutable)
    except SQLAlchemyError:
        logger.warning("provider_cache_unavailable")
