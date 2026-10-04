"""SMTP delivery, used with a Gmail app password while no domain exists.

The connection is injected, so these tests never open a socket. What they pin
is the order that keeps the credential safe (TLS before login), the message
the recipient actually receives, and errors that leak nothing into logs.
"""

import smtplib
import ssl
from email.message import EmailMessage as MimeMessage

import pytest

from app.services.email.sender import EmailDeliveryError, EmailMessage
from app.services.email.smtp import SmtpEmailSender

MESSAGE = EmailMessage(
    to="user@example.com",
    subject="Verify your address",
    text="Open https://vantage.example/verify-email?token=secret-token-value",
)
PASSWORD = "abcd efgh ijkl mnop"


class FakeSmtp:
    def __init__(
        self,
        *,
        starttls_error: Exception | None = None,
        send_error: Exception | None = None,
    ) -> None:
        self.calls: list[str] = []
        self.sent: list[MimeMessage] = []
        self.login_args: tuple[str, str] | None = None
        self.tls_context: ssl.SSLContext | None = None
        self._starttls_error = starttls_error
        self._send_error = send_error

    def __enter__(self) -> "FakeSmtp":
        return self

    def __exit__(self, *exc: object) -> None:
        self.calls.append("quit")

    def starttls(self, *, context: ssl.SSLContext) -> None:
        self.calls.append("starttls")
        self.tls_context = context
        if self._starttls_error:
            raise self._starttls_error

    def login(self, user: str, password: str) -> None:
        self.calls.append("login")
        self.login_args = (user, password)

    def send_message(self, message: MimeMessage) -> None:
        self.calls.append("send")
        if self._send_error:
            raise self._send_error
        self.sent.append(message)


def _sender(
    fake: FakeSmtp, *, port: int = 587, opened: list | None = None
) -> SmtpEmailSender:
    def connect(host: str, port: int, timeout: int, implicit_tls: bool) -> FakeSmtp:
        if opened is not None:
            opened.append((host, port, timeout, implicit_tls))
        return fake

    return SmtpEmailSender(
        host="smtp.gmail.com",
        port=port,
        username="vantage.noreply.support@gmail.com",
        password=PASSWORD,
        sender="Vantage <vantage.noreply.support@gmail.com>",
        timeout_seconds=10,
        connect=connect,
    )


def test_port_587_upgrades_to_tls_before_logging_in() -> None:
    fake = FakeSmtp()
    opened: list = []
    _sender(fake, opened=opened).send(MESSAGE)
    assert opened == [("smtp.gmail.com", 587, 10, False)]
    assert fake.calls == ["starttls", "login", "send", "quit"]
    assert fake.login_args == ("vantage.noreply.support@gmail.com", PASSWORD)


def test_tls_verifies_the_server_certificate() -> None:
    fake = FakeSmtp()
    _sender(fake).send(MESSAGE)
    assert fake.tls_context is not None
    assert fake.tls_context.verify_mode == ssl.CERT_REQUIRED
    assert fake.tls_context.check_hostname is True


def test_port_465_uses_implicit_tls_without_starttls() -> None:
    fake = FakeSmtp()
    opened: list = []
    _sender(fake, port=465, opened=opened).send(MESSAGE)
    assert opened == [("smtp.gmail.com", 465, 10, True)]
    assert fake.calls == ["login", "send", "quit"]


def test_the_password_is_never_sent_without_tls() -> None:
    # A server that cannot upgrade would receive the app password in clear.
    fake = FakeSmtp(starttls_error=smtplib.SMTPNotSupportedError("no STARTTLS"))
    with pytest.raises(EmailDeliveryError):
        _sender(fake).send(MESSAGE)
    assert "login" not in fake.calls


def test_the_recipient_receives_the_configured_sender_subject_and_body() -> None:
    fake = FakeSmtp()
    _sender(fake).send(MESSAGE)
    [sent] = fake.sent
    assert sent["From"] == "Vantage <vantage.noreply.support@gmail.com>"
    assert sent["To"] == "user@example.com"
    assert sent["Subject"] == "Verify your address"
    assert (
        "verify-email?token=secret-token-value"
        in sent.get_body(("plain",)).get_content()
    )


def test_an_html_body_is_sent_as_an_alternative_part() -> None:
    fake = FakeSmtp()
    _sender(fake).send(
        EmailMessage(
            to="user@example.com", subject="S", text="plain", html="<p>rich</p>"
        )
    )
    [sent] = fake.sent
    assert sent.get_body(("plain",)).get_content().strip() == "plain"
    assert "<p>rich</p>" in sent.get_body(("html",)).get_content()


@pytest.mark.parametrize(
    "error",
    [
        smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted"),
        smtplib.SMTPDataError(550, b"Daily user sending limit exceeded"),
        TimeoutError("timed out"),
        ConnectionRefusedError("refused"),
    ],
)
def test_failures_raise_delivery_errors_that_leak_nothing(error: Exception) -> None:
    fake = FakeSmtp(send_error=error)
    with pytest.raises(EmailDeliveryError) as raised:
        _sender(fake).send(MESSAGE)
    rendered = str(raised.value)
    assert "user@example.com" not in rendered
    assert "secret-token-value" not in rendered
    assert PASSWORD not in rendered


def test_a_connection_failure_raises_a_delivery_error() -> None:
    def connect(host: str, port: int, timeout: int, implicit_tls: bool) -> FakeSmtp:
        raise OSError("network unreachable")

    sender = SmtpEmailSender(
        host="smtp.gmail.com",
        port=587,
        username="u@gmail.com",
        password=PASSWORD,
        sender="Vantage <u@gmail.com>",
        connect=connect,
    )
    with pytest.raises(EmailDeliveryError):
        sender.send(MESSAGE)
