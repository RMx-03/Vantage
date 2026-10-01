from app.services.email.templates import (
    duplicate_registration_message,
    password_reset_message,
    verification_message,
)


def test_verification_message_contains_the_link() -> None:
    message = verification_message("user@example.com", "tok-abc")
    assert "/verify-email?token=tok-abc" in message.text
    assert message.to == "user@example.com"


def test_verification_message_states_the_expiry() -> None:
    assert "24 hours" in verification_message("user@example.com", "t").text


def test_reset_message_contains_the_link_and_expiry() -> None:
    message = password_reset_message("user@example.com", "tok-xyz")
    assert "/reset-password?token=tok-xyz" in message.text
    assert "60 minutes" in message.text


def test_reset_message_tells_the_reader_what_to_do_if_they_did_not_ask() -> None:
    # If the request was not theirs, the message must not read as an
    # instruction to act.
    assert "ignore" in password_reset_message("user@example.com", "t").text.lower()


def test_duplicate_registration_message_does_not_contain_a_link() -> None:
    # Sent to an address that is already registered. It must not hand an
    # attacker who guessed the address anything actionable.
    message = duplicate_registration_message("user@example.com")
    assert "token" not in message.text.lower()
    assert "http" not in message.text.lower().replace("https://vantage", "")


def test_messages_do_not_claim_to_be_investment_advice() -> None:
    for message in (
        verification_message("u@example.com", "t"),
        password_reset_message("u@example.com", "t"),
    ):
        lowered = message.text.lower()
        assert "advice" not in lowered
        assert "recommend" not in lowered
