import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from uuid import UUID

from app.core.config import settings
from app.domain.errors import (
    RUN_CAPACITY_EXCEEDED,
    RUN_CAPACITY_EXCEEDED_MESSAGE,
    SERVICE_DRAINING,
    SERVICE_DRAINING_MESSAGE,
    VantageError,
)

logger = logging.getLogger(__name__)


class RunExecutor:
    """Bounded in-process pool for detached research runs.

    Capacity is tracked here, not through the pool queue, so a full executor
    refuses work instead of queueing it.
    """

    def __init__(self, max_workers: int) -> None:
        self._max_workers = max_workers
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="research-run"
        )
        self._cond = threading.Condition()
        self._held = 0
        self._running: set[UUID] = set()
        self._draining = False

    @property
    def in_flight_count(self) -> int:
        with self._cond:
            return self._held

    def reserve(self) -> "RunSlot":
        with self._cond:
            if self._draining:
                raise VantageError(
                    code=SERVICE_DRAINING,
                    safe_message=SERVICE_DRAINING_MESSAGE,
                    retryable=True,
                )
            if self._held >= self._max_workers:
                raise VantageError(
                    code=RUN_CAPACITY_EXCEEDED,
                    safe_message=RUN_CAPACITY_EXCEEDED_MESSAGE,
                    retryable=True,
                )
            self._held += 1
        return RunSlot(self)

    def is_in_flight(self, run_id: UUID) -> bool:
        with self._cond:
            return run_id in self._running

    def begin_drain(self) -> None:
        with self._cond:
            self._draining = True

    def wait_idle(self, timeout: float) -> bool:
        with self._cond:
            return self._cond.wait_for(lambda: self._held == 0, timeout=timeout)

    def _free(self, run_id: UUID | None) -> None:
        with self._cond:
            if run_id is not None:
                self._running.discard(run_id)
            self._held -= 1
            if self._held == 0:
                self._cond.notify_all()


class RunSlot:
    def __init__(self, executor: RunExecutor) -> None:
        self._executor = executor
        self._done = False
        self._lock = threading.Lock()

    def _claim(self) -> bool:
        with self._lock:
            if self._done:
                return False
            self._done = True
            return True

    def launch(self, run_id: UUID, fn: Callable[[], None]) -> None:
        if not self._claim():
            raise RuntimeError("run slot already used")
        executor = self._executor
        with executor._cond:
            executor._running.add(run_id)

        def _work() -> None:
            try:
                fn()
            except Exception as exc:
                logger.error(
                    "detached research run failed",
                    extra={"run_id": str(run_id), "error_type": type(exc).__name__},
                )
            finally:
                executor._free(run_id)

        try:
            executor._pool.submit(_work)
        except BaseException:
            executor._free(run_id)
            raise

    def release(self) -> None:
        if self._claim():
            self._executor._free(None)


@lru_cache(maxsize=1)
def get_run_executor() -> RunExecutor:
    return RunExecutor(settings.RUN_EXECUTOR_MAX_WORKERS)
