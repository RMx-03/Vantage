"""Postgres-backed provider request cache with a throttled seven-day purge."""

import time
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert

from app.db.models import ProviderCacheRow
from app.db.session import SessionFactory
from app.providers.cache import CacheEntry, compute_content_hash


class PostgresProviderCache:
    """Database errors propagate: the calling provider decides what they mean."""

    def __init__(
        self,
        session_factory: Any = SessionFactory,
        *,
        purge_interval_seconds: float = 3600,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._session_factory = session_factory
        self._purge_interval = purge_interval_seconds
        self._clock = clock
        self._last_purge: float | None = None

    def get(
        self, provider: str, cache_key: str, valid_for_date: date
    ) -> CacheEntry | None:
        with self._session_factory() as session:
            row = session.execute(
                select(ProviderCacheRow).where(
                    ProviderCacheRow.provider == provider,
                    ProviderCacheRow.cache_key == cache_key,
                    ProviderCacheRow.valid_for_date == valid_for_date,
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return CacheEntry(row.payload, row.content_hash, row.retrieved_at)

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
        content_hash = compute_content_hash(payload)
        stmt = insert(ProviderCacheRow).values(
            provider=provider,
            cache_key=cache_key,
            valid_for_date=valid_for_date,
            content_hash=content_hash,
            payload=payload,
            retrieved_at=retrieved_at,
            immutable=immutable,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_provider_cache_key",
            set_={
                "content_hash": stmt.excluded.content_hash,
                "payload": stmt.excluded.payload,
                "retrieved_at": stmt.excluded.retrieved_at,
                "immutable": stmt.excluded.immutable,
            },
        )
        with self._session_factory() as session, session.begin():
            session.execute(stmt)
            if self._purge_due():
                session.execute(
                    delete(ProviderCacheRow).where(
                        ProviderCacheRow.retrieved_at
                        < func.now() - text("interval '7 days'"),
                        ProviderCacheRow.immutable.is_(False),
                    )
                )
        return CacheEntry(payload, content_hash, retrieved_at)

    def _purge_due(self) -> bool:
        now = self._clock()
        if (
            self._last_purge is not None
            and now - self._last_purge < self._purge_interval
        ):
            return False
        self._last_purge = now
        return True
