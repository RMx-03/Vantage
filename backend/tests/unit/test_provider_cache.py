from datetime import UTC, date, datetime

from app.providers.cache import InMemoryProviderCache, compute_content_hash

DAY = date(2026, 11, 13)
NOW = datetime(2026, 11, 14, tzinfo=UTC)


def test_in_memory_round_trip() -> None:
    cache = InMemoryProviderCache()
    stored = cache.put("edgar", "k", DAY, {"a": 1}, NOW)
    fetched = cache.get("edgar", "k", DAY)
    assert fetched == stored
    assert fetched is not None and fetched.payload == {"a": 1}
    assert fetched.retrieved_at == NOW


def test_different_valid_for_date_misses() -> None:
    cache = InMemoryProviderCache()
    cache.put("edgar", "k", DAY, {"a": 1}, NOW)
    assert cache.get("edgar", "k", date(2026, 11, 12)) is None


def test_content_hash_is_stable_across_key_order() -> None:
    assert compute_content_hash({"a": 1, "b": 2}) == compute_content_hash(
        {"b": 2, "a": 1}
    )
    assert compute_content_hash({"a": 1}) != compute_content_hash({"a": 2})
