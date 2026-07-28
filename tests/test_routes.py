"""Tests for Africa's Talking webhook behavior."""

from typing import Any
from xml.etree.ElementTree import fromstring

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_ussd_first_request_returns_main_menu() -> None:
    """Ensure a new USSD session receives a continuing main menu."""

    response = client.post(
        "/ussd",
        data={
            "sessionId": "session-1",
            "phoneNumber": "+254700000001",
            "serviceCode": "*384*123#",
            "text": "",
        },
    )

    assert response.status_code == 200
    assert response.text.startswith("CON Scripture Without Screens")
    assert "1. Verse of the Day" in response.text


def test_ussd_verse_response_ends_within_limit(monkeypatch: Any) -> None:
    """Ensure the Verse of the Day closes the session within 160 characters."""

    monkeypatch.setattr(
        "app.routes.ussd.get_verse_of_the_day",
        lambda: "For God so loved the world " * 20,
    )

    response = client.post(
        "/ussd",
        data={
            "sessionId": "session-2",
            "phoneNumber": "+254700000001",
            "serviceCode": "*384*123#",
            "text": "1",
        },
    )

    assert response.status_code == 200
    assert response.text.startswith("END ")
    assert len(response.text) <= 160


def test_sms_mood_sends_personalized_reply(monkeypatch: Any) -> None:
    """Ensure a recognized mood generates and sends an SMS reflection."""

    sent: dict[str, Any] = {}
    monkeypatch.setattr(
        "app.routes.sms.get_verse_of_the_day",
        lambda: "Be still, and know that I am God.",
    )
    monkeypatch.setattr(
        "app.routes.sms.generate_reflection",
        lambda verse, mood=None: f"Reflection for {mood}: {verse}",
    )

    def fake_send_sms(
        message: str, recipient: str, sender_id: str | None = None
    ) -> dict[str, Any]:
        """Capture outbound SMS arguments for assertions.

        Args:
            message: Text that would be sent.
            recipient: Destination subscriber number.
            sender_id: Optional originating shortcode.

        Returns:
            A representative successful SDK response.
        """

        sent.update(
            message=message,
            recipient=recipient,
            sender_id=sender_id,
        )
        return {"SMSMessageData": {"Recipients": []}}

    monkeypatch.setattr("app.routes.sms.send_sms", fake_send_sms)

    response = client.post(
        "/sms",
        data={
            "from": "+254700000002",
            "to": "12345",
            "text": "stressed",
        },
    )

    assert response.status_code == 200
    assert response.text == "GOOD"
    assert sent["recipient"] == "+254700000002"
    assert sent["sender_id"] == "12345"
    assert "STRESSED" in sent["message"]
    assert len(sent["message"]) <= 160


def test_sms_unknown_word_sends_usage_hint(monkeypatch: Any) -> None:
    """Ensure unsupported text receives a concise list of mood choices."""

    sent: dict[str, Any] = {}

    def fake_send_sms(
        message: str, recipient: str, sender_id: str | None = None
    ) -> dict[str, Any]:
        """Capture the usage hint instead of contacting Africa's Talking.

        Args:
            message: Text that would be sent.
            recipient: Destination subscriber number.
            sender_id: Optional originating shortcode.

        Returns:
            A representative successful SDK response.
        """

        sent["message"] = message
        return {"SMSMessageData": {"Recipients": []}}

    monkeypatch.setattr("app.routes.sms.send_sms", fake_send_sms)

    response = client.post(
        "/sms",
        data={
            "from": "+254700000003",
            "to": "12345",
            "text": "hello",
        },
    )

    assert response.status_code == 200
    assert response.text == "GOOD"
    assert sent["message"] == (
        "Reply STRESSED, GRATEFUL, or TIRED for a short reflection."
    )


def test_voice_first_callback_returns_keypad_menu() -> None:
    """Ensure a new active call receives valid GetDigits XML."""

    response = client.post(
        "/voice",
        data={
            "sessionId": "call-1",
            "callerNumber": "+254700000004",
            "destinationNumber": "+254711000000",
            "isActive": "1",
        },
    )

    root = fromstring(response.text)
    get_digits = root.find("GetDigits")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert root.tag == "Response"
    assert get_digits is not None
    assert get_digits.attrib["numDigits"] == "1"
    assert "Press 1" in get_digits.findtext("Say", default="")


def test_voice_option_one_reads_escaped_verse(monkeypatch: Any) -> None:
    """Ensure option 1 reads scripture and safely escapes XML characters."""

    monkeypatch.setattr(
        "app.routes.voice.get_verse_of_the_day",
        lambda: "Grace & peace are with you.",
    )

    response = client.post(
        "/voice",
        data={
            "sessionId": "call-2",
            "callerNumber": "+254700000004",
            "destinationNumber": "+254711000000",
            "isActive": "1",
            "dtmfDigits": "1",
        },
    )

    root = fromstring(response.text)

    assert response.status_code == 200
    assert root.findtext("Say") == "Grace & peace are with you."
    assert "&amp;" in response.text
