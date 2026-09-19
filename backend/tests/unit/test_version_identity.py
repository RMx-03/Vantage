from unittest.mock import MagicMock

from app.core.config import settings
from app.services.research_run import ResearchRunService


def test_version_info_tracks_code_revision_not_display_version(monkeypatch) -> None:
    """The recorded code version is the immutable artifact revision, never the
    semantic product version shown by the API."""
    monkeypatch.setattr(settings, "CODE_REVISION", "0f1e2d3c4b5a")

    service = ResearchRunService(
        repo=MagicMock(),
        market_provider=MagicMock(),
        news_provider=MagicMock(),
        interpretation_provider=MagicMock(),
    )

    assert service.versions.code == "0f1e2d3c4b5a"
    assert service.versions.code != settings.APP_VERSION
