import logging
import threading
from uuid import uuid4

import pytest

from app.domain.errors import VantageError
from app.services.run_executor import RunExecutor


def _gated(started: threading.Event, gate: threading.Event):
    def fn() -> None:
        started.set()
        assert gate.wait(5)

    return fn


def test_reserve_beyond_capacity_raises_retryable_capacity_error() -> None:
    executor = RunExecutor(max_workers=2)
    executor.reserve()
    executor.reserve()
    with pytest.raises(VantageError) as exc:
        executor.reserve()
    assert exc.value.code == "RUN_CAPACITY_EXCEEDED"
    assert exc.value.retryable is True


def test_released_slot_can_be_reserved_again() -> None:
    executor = RunExecutor(max_workers=1)
    slot = executor.reserve()
    slot.release()
    slot.release()  # idempotent
    executor.reserve()
    with pytest.raises(VantageError):
        executor.reserve()


def test_launch_tracks_run_until_fn_returns() -> None:
    executor = RunExecutor(max_workers=1)
    run_id = uuid4()
    started, gate = threading.Event(), threading.Event()
    executor.reserve().launch(run_id, _gated(started, gate))
    assert started.wait(2)
    assert executor.is_in_flight(run_id) is True
    assert executor.in_flight_count == 1
    gate.set()
    assert executor.wait_idle(2) is True
    assert executor.is_in_flight(run_id) is False
    assert executor.in_flight_count == 0


def test_exception_in_fn_frees_slot_and_logs_without_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    executor = RunExecutor(max_workers=1)

    def boom() -> None:
        raise RuntimeError("secret-token-abc")

    with caplog.at_level(logging.DEBUG):
        executor.reserve().launch(uuid4(), boom)
        assert executor.wait_idle(2) is True
    executor.reserve()
    messages = [r.getMessage() for r in caplog.records]
    assert any(
        m.startswith("detached research run failed run_id=")
        and m.endswith("error_type=RuntimeError")
        for m in messages
    ), messages
    for record in caplog.records:
        assert "secret-token-abc" not in record.getMessage()
        assert "secret-token-abc" not in str(record.__dict__)
        assert record.exc_info is None


def test_drain_rejects_new_reservations() -> None:
    executor = RunExecutor(max_workers=1)
    executor.begin_drain()
    with pytest.raises(VantageError) as exc:
        executor.reserve()
    assert exc.value.code == "SERVICE_DRAINING"
    assert exc.value.retryable is True


def test_wait_idle_returns_false_on_timeout() -> None:
    executor = RunExecutor(max_workers=1)
    started, gate = threading.Event(), threading.Event()
    executor.reserve().launch(uuid4(), _gated(started, gate))
    assert started.wait(2)
    assert executor.wait_idle(0.05) is False
    gate.set()
    assert executor.wait_idle(2) is True


def test_launch_after_shutdown_raises_and_frees_the_slot() -> None:
    executor = RunExecutor(max_workers=1)
    executor.shutdown()
    with pytest.raises(RuntimeError):
        executor.reserve().launch(uuid4(), lambda: None)
    assert executor.in_flight_count == 0
