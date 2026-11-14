from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import app.main as main
from app.core.config import settings


def test_shutdown_drains_executor(monkeypatch) -> None:
    spy = MagicMock()
    spy.wait_idle.return_value = True
    factory = MagicMock(return_value=spy)
    monkeypatch.setattr(main, "get_run_executor", factory)

    with TestClient(main.app):
        factory.cache_clear.assert_called_once_with()
        spy.begin_drain.assert_not_called()

    spy.begin_drain.assert_called_once_with()
    spy.wait_idle.assert_called_once_with(settings.RUN_SHUTDOWN_GRACE_SECONDS)
    spy.shutdown.assert_called_once_with()
