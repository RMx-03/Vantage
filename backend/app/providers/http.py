"""Shared HTTP helper for data providers.

Errors carry only a fixed kind and a status code. They never include a URL, query
parameters, headers or httpx exception text, so an API key cannot reach a message, a
repr, an exception chain or a log line. Raises happen outside any ``except`` block, so
both ``__cause__`` and ``__context__`` are None.
"""

import logging
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from typing import Any, Literal

import httpx

from app.domain.errors import VantageError

logger = logging.getLogger(__name__)

# httpx logs full request URLs at INFO, which would include query-borne keys (FRED).
logging.getLogger("httpx").setLevel(logging.WARNING)
# h11 error text can carry a header value (a key or contact address) and httpcore
# writes it at DEBUG, so hold that logger at WARNING too.
logging.getLogger("httpcore").setLevel(logging.WARNING)

ErrorKind = Literal[
    "auth", "rate_limited", "unavailable", "rejected", "not_found", "malformed"
]

_MIN_RETRY_BUDGET_SECONDS = 1.0
_MAX_RETRY_AFTER_SECONDS = 2


class ProviderHttpError(Exception):
    def __init__(self, kind: ErrorKind, status: int | None = None) -> None:
        super().__init__(kind)
        self.kind: ErrorKind = kind
        self.status = status


def _error(kind: ErrorKind, status: int | None = None) -> ProviderHttpError:
    logger.warning("provider_http_error kind=%s status=%s", kind, status)
    return ProviderHttpError(kind, status)


class RateLimiter:
    """Sliding-window limiter. Waits up to ``max_wait_seconds``, then refuses."""

    def __init__(
        self,
        max_calls: int,
        period_seconds: float,
        *,
        max_wait_seconds: float = 2.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._max_calls = max_calls
        self._period = period_seconds
        self._max_wait = max_wait_seconds
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._calls: deque[float] = deque()

    def acquire(self) -> None:
        waited = 0.0
        while True:
            with self._lock:
                now = self._clock()
                while self._calls and now - self._calls[0] >= self._period:
                    self._calls.popleft()
                if len(self._calls) < self._max_calls:
                    self._calls.append(now)
                    return
                wait = self._calls[0] + self._period - now
            if waited + wait > self._max_wait:
                raise _error("rate_limited")
            self._sleep(wait)
            waited += wait


def _kind_for_status(status: int) -> ErrorKind | None:
    if status in (401, 403):
        return "auth"
    if status == 404:
        return "not_found"
    if status == 429:
        return "rate_limited"
    if 300 <= status < 400:
        return "rejected"  # redirects are not followed
    if status >= 500:
        return "unavailable"
    if status >= 400:
        return "rejected"
    return None


class ProviderHttp:
    def __init__(
        self,
        *,
        timeout_seconds: float,
        limiter: RateLimiter,
        headers: Mapping[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        retry_backoff_seconds: float = 0.5,
    ) -> None:
        self._timeout = timeout_seconds
        self._limiter = limiter
        self._clock = clock
        self._sleep = sleep
        self._backoff = retry_backoff_seconds
        self._client = httpx.Client(headers=dict(headers or {}), transport=transport)

    def close(self) -> None:
        self._client.close()

    def deadline(self) -> float:
        """Absolute clock time that ends one provider call made of several requests."""
        return self._clock() + self._timeout

    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        deadline: float | None = None,
    ) -> Any:
        response = self._get(url, params, deadline)
        try:
            return response.json()
        except ValueError:
            pass
        # Raised outside the except block so no exception is left in __context__.
        raise _error("malformed", response.status_code)

    def get_text(
        self,
        url: str,
        *,
        params: Mapping[str, str] | None = None,
        deadline: float | None = None,
    ) -> str:
        return self._get(url, params, deadline).text

    def _get(
        self,
        url: str,
        params: Mapping[str, str] | None,
        deadline: float | None = None,
    ) -> httpx.Response:
        start = self._clock()
        attempt = 0
        while True:
            if deadline is not None and deadline - self._clock() <= 0:
                raise _error("unavailable")
            self._limiter.acquire()
            remaining = self._timeout - (self._clock() - start)
            if deadline is not None:
                remaining = min(remaining, deadline - self._clock())
            remaining = max(remaining, 0.001)
            kind: ErrorKind | None
            status: int | None = None
            retry_delay = self._backoff
            try:
                response = self._client.get(
                    url, params=dict(params) if params else None, timeout=remaining
                )
            except (httpx.TimeoutException, httpx.TransportError):
                kind = "unavailable"
            except httpx.InvalidURL:
                kind = "rejected"
            except httpx.HTTPError:
                # Corrupt body or redirect loop: not retryable. The kind is raised
                # below, outside this block, so no httpx text enters __context__.
                kind = "malformed"
            else:
                status = response.status_code
                kind = _kind_for_status(status)
                if kind is None:
                    return response
                if status == 429:
                    retry_delay = _retry_after(response, self._backoff)
            retryable = kind in ("rate_limited", "unavailable")
            budget_left = self._timeout - (self._clock() - start)
            if deadline is not None:
                budget_left = min(budget_left, deadline - self._clock())
            budget_left -= retry_delay
            if attempt == 0 and retryable and budget_left >= _MIN_RETRY_BUDGET_SECONDS:
                self._sleep(retry_delay)
                attempt += 1
                continue
            raise _error(kind, status)


def _retry_after(response: httpx.Response, default: float) -> float:
    value = response.headers.get("Retry-After", "")
    if value.isdigit() and int(value) <= _MAX_RETRY_AFTER_SECONDS:
        return float(int(value))
    return default


def fail(
    code: str, messages: Mapping[str, str], err: ProviderHttpError
) -> VantageError:
    """Build the safe domain error.

    Callers write ``raise fail(...) from None``. If they do so inside an ``except
    ProviderHttpError`` block, the context is that error, which carries no secret.
    """
    return VantageError(
        code=code,
        safe_message=messages[err.kind],
        retryable=err.kind in {"rate_limited", "unavailable"},
    )
