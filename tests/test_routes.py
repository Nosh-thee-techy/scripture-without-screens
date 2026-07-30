"""Tests for Africa's Talking webhook behavior."""

from typing import Any
from xml.etree.ElementTree import fromstring

from fastapi.testclient import TestClient

from app.main import app
from app.utils.session_store import clear_user_session, get_user_session


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
    assert "2. Reading Plan" in response.text
    assert "4. Change Bible Version" in response.text


def test_ussd_reading_plan_submenu_and_switch(monkeypatch: Any) -> None:
    """Ensure plan continue advances day and choose-plan resets progress."""

    phone = "+254700000088"
    clear_user_session(phone)

    monkeypatch.setattr(
        "app.routes.ussd.get_passage",
        lambda reference, language="en", bible_id=None: f"Passage {reference}",
    )

    submenu = client.post(
        "/ussd",
        data={
            "sessionId": "session-plan",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "2",
        },
    )
    assert submenu.text.startswith("CON Reading Plan")
    assert "Continue today" in submenu.text

    day_one = client.post(
        "/ussd",
        data={
            "sessionId": "session-plan",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "2*1",
        },
    )
    assert day_one.text.startswith("END ")
    assert "D1:" in day_one.text
    assert get_user_session(phone)["plan_day"] == 2

    choose = client.post(
        "/ussd",
        data={
            "sessionId": "session-plan-2",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "2*2",
        },
    )
    assert choose.text.startswith("CON Choose plan:")
    assert "Daily Strength" in choose.text

    switched = client.post(
        "/ussd",
        data={
            "sessionId": "session-plan-2",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "2*2*2",
        },
    )
    assert "Daily Strength" in switched.text
    assert get_user_session(phone)["plan_id"] == "strength"
    assert get_user_session(phone)["plan_day"] == 1


def test_ussd_verse_response_ends_within_limit(monkeypatch: Any) -> None:
    """Ensure the Verse of the Day closes the session within 160 characters."""

    monkeypatch.setattr(
        "app.routes.ussd.get_verse_of_the_day",
        lambda language="en", bible_id=None: "For God so loved the world " * 20,
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


def test_ussd_change_language_persists_in_session() -> None:
    """Ensure language choice is stored for later dials."""

    phone = "+254700000099"
    clear_user_session(phone)

    menu = client.post(
        "/ussd",
        data={
            "sessionId": "session-lang",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "3",
        },
    )
    assert menu.text.startswith("CON Choose language:")
    assert "Kalenjin" in menu.text

    confirm = client.post(
        "/ussd",
        data={
            "sessionId": "session-lang",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "3*3",
        },
    )
    assert confirm.status_code == 200
    assert "Kalenjin" in confirm.text
    assert get_user_session(phone)["language"] == "kln"
    assert get_user_session(phone)["bible_id"] is None


def test_sms_mood_sends_personalized_reply(monkeypatch: Any) -> None:
    """Ensure a recognized mood generates and sends an SMS reflection."""

    sent: dict[str, Any] = {}
    monkeypatch.setattr(
        "app.routes.sms.get_verse_of_the_day",
        lambda language="en", bible_id=None: "Be still, and know that I am God.",
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


def test_demo_sms_returns_reflection_body(monkeypatch: Any) -> None:
    """Ensure the judge SMS preview returns the message without sending."""

    monkeypatch.setattr(
        "app.routes.sms.get_verse_of_the_day",
        lambda language="en", bible_id=None: "Be still, and know that I am God.",
    )
    monkeypatch.setattr(
        "app.routes.sms.generate_reflection",
        lambda verse, mood=None: f"Reflection for {mood}: {verse}",
    )

    response = client.post(
        "/demo/sms",
        data={"from": "+254700000010", "text": "grateful"},
    )

    assert response.status_code == 200
    assert "GRATEFUL" in response.text
    assert len(response.text) <= 160


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
        lambda language="en", bible_id=None: "Grace & peace are with you.",
    )
    # Force the Africa's Talking Say fallback so the test stays offline.
    monkeypatch.setattr(
        "app.routes.voice.synthesize_speech",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            __import__(
                "app.services.elevenlabs_client", fromlist=["ElevenLabsError"]
            ).ElevenLabsError("forced offline")
        ),
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
