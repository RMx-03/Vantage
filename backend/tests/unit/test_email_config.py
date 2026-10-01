"""Email configuration must fail at startup, not on the first send.

A missing BREVO_API_KEY used to surface inside /register, after the user row
was committed: the caller got a 500, the account existed but was unverified,
and every resend failed the same way. An unknown provider name silently fell
back to the no-op sender, so production would send nothing while the UI said a
message was on its way.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings


def _boot() -> None:
    from app.main import app

    with TestClient(app):
        pass


def test_brevo_without_a_key_refuses_to_start(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "brevo")
    monkeypatch.setattr(settings, "BREVO_API_KEY", "")
    monkeypatch.setattr(settings, "EMAIL_FROM", "Vantage <sender@example.com>")
    with pytest.raises(RuntimeError, match="BREVO_API_KEY"):
        _boot()


def test_an_unknown_provider_refuses_to_start(monkeypatch: pytest.MonkeyPatch) -> None:
    # "resend" was the original plan's provider. A leftover value must not
    # quietly turn every email into a no-op.
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "resend")
    with pytest.raises(RuntimeError, match="EMAIL_PROVIDER"):
        _boot()


def test_brevo_with_the_placeholder_sender_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Brevo rejects mail from an unverified sender; the shipped default is one.
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "brevo")
    monkeypatch.setattr(settings, "BREVO_API_KEY", "xkeysib-test-value")
    monkeypatch.setattr(settings, "EMAIL_FROM", "Vantage <noreply@example.invalid>")
    with pytest.raises(RuntimeError, match="EMAIL_FROM"):
        _boot()


def test_a_complete_brevo_configuration_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "brevo")
    monkeypatch.setattr(settings, "BREVO_API_KEY", "xkeysib-test-value")
    monkeypatch.setattr(settings, "EMAIL_FROM", "Vantage <sender@example.com>")
    _boot()


def test_the_noop_provider_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "noop")
    _boot()
