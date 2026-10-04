import logging

import httpx
import pytest

from app.services.email.brevo import BrevoEmailSender
from app.services.email.noop import NoopEmailSender
from app.services.email.sender import EmailDeliveryError, EmailMessage

MESSAGE = EmailMessage(
    to="user@example.com",
    subject="Verify your address",
    text="Open https://vantage.example/verify-email?token=secret-token-value",
)


def test_noop_sender_logs_without_sending(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        NoopEmailSender().send(MESSAGE)
    assert any("email.suppressed" in record.message for record in caplog.records)


def test_noop_sender_never_logs_the_token(caplog: pytest.LogCaptureFixture) -> None:
    # A logged reset link is a password reset anyone with log access can use.
    with caplog.at_level(logging.DEBUG):
        NoopEmailSender().send(MESSAGE)
    assert "secret-token-value" not in caplog.text


def test_resend_sender_posts_the_expected_payload() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["api_key"] = request.headers.get("api-key")
        captured["body"] = request.read().decode()
        return httpx.Response(201, json={"messageId": "<abc@smtp-relay.brevo.com>"})

    sender = BrevoEmailSender(
        api_key="test-key",
        sender="Vantage <noreply@example.test>",
        transport=httpx.MockTransport(handler),
    )
    sender.send(MESSAGE)

    assert captured["url"] == "https://api.brevo.com/v3/smtp/email"
    assert captured["api_key"] == "test-key"
    body = str(captured["body"])
    assert "user@example.com" in body
    # Brevo-specific field names — getting these wrong fails at runtime only.
    assert "textContent" in body
    assert "sender" in body


def test_resend_sender_raises_on_rejection() -> None:
    sender = BrevoEmailSender(
        api_key="test-key",
        sender="Vantage <noreply@example.test>",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(422, json={"message": "bad"})
        ),
    )
    with pytest.raises(EmailDeliveryError):
        sender.send(MESSAGE)


def test_resend_sender_raises_on_rate_limit() -> None:
    # Brevo's free tier caps at 300/day. Hitting it must be loud, not silent.
    sender = BrevoEmailSender(
        api_key="test-key",
        sender="Vantage <noreply@example.test>",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(429, json={"message": "slow"})
        ),
    )
    with pytest.raises(EmailDeliveryError):
        sender.send(MESSAGE)


def test_resend_sender_raises_on_transport_failure() -> None:
    def boom(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable")

    sender = BrevoEmailSender(
        api_key="test-key",
        sender="Vantage <noreply@example.test>",
        transport=httpx.MockTransport(boom),
    )
    with pytest.raises(EmailDeliveryError):
        sender.send(MESSAGE)


def test_error_message_does_not_leak_the_recipient() -> None:
    sender = BrevoEmailSender(
        api_key="test-key",
        sender="Vantage <noreply@example.test>",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(500, json={"message": "x"})
        ),
    )
    with pytest.raises(EmailDeliveryError) as excinfo:
        sender.send(MESSAGE)
    assert "user@example.com" not in str(excinfo.value)
