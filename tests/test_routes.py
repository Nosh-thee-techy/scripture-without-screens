"""Tests for Africa's Talking webhook behavior."""

from typing import Any
from xml.etree.ElementTree import fromstring

from fastapi.testclient import TestClient

from app.main import app
from app.utils.session_store import (
    clear_user_session,
    get_user_session,
    update_user_session,
)


client = TestClient(app)


def _onboard(phone: str, language_choice: str = "1") -> None:
    """Clear Redis prefs and complete first-time language onboarding."""

    clear_user_session(phone)
    welcome = client.post(
        "/ussd",
        data={
            "sessionId": "onboard",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "",
        },
    )
    assert "Choose language" in welcome.text
    confirm = client.post(
        "/ussd",
        data={
            "sessionId": "onboard",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": language_choice,
        },
    )
    assert "Scripture Without Screens" in confirm.text
    assert get_user_session(phone)["language_set"] is True


def test_whatsapp_webhook_verifies_with_token() -> None:
    """Ensure Meta's hub.challenge handshake succeeds with our verify token."""

    response = client.get(
        "/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "sws-whatsapp-verify",
            "hub.challenge": "challenge-123",
        },
    )
    assert response.status_code == 200
    assert response.text == "challenge-123"

    denied = client.get(
        "/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong",
            "hub.challenge": "challenge-123",
        },
    )
    assert denied.status_code == 403


def _wa_text(reply: Any) -> str:
    """Flatten WhatsApp text/image parts into searchable text."""

    if isinstance(reply, str):
        return reply
    chunks: list[str] = []
    for part in reply:
        if part.get("type") == "text":
            chunks.append(str(part.get("body") or ""))
        elif part.get("type") == "image":
            chunks.append(str(part.get("caption") or ""))
            chunks.append(str(part.get("url") or ""))
    return "\n".join(chunks)


def test_whatsapp_votd_offers_explain_pray_chapter_compare(monkeypatch: Any) -> None:
    """Ensure WhatsApp VOTD is not verse-only; options follow the verse."""

    from app.routes import whatsapp as wa

    phone = "+254700000201"
    clear_user_session(phone)
    update_user_session(
        phone, language_set=True, language="en", wa_flow="main"
    )
    monkeypatch.setattr(
        wa,
        "get_verse_of_the_day_detail",
        lambda language="en", bible_id=None: {
            "passage_id": "PRO.18.21",
            "reference": "Proverbs 18:21",
            "text": "Death and life are in the power of the tongue.",
        },
    )
    reply = _wa_text(wa._build_reply(phone, "1"))
    assert "Proverbs 18:21" in reply
    assert "Explain this verse" in reply
    assert "Pray with me" in reply
    assert "Read full chapter" in reply
    assert "Compare Bible versions" in reply
    assert get_user_session(phone)["wa_flow"] == "votd"

    monkeypatch.setattr(
        wa,
        "explain_scripture",
        lambda reference, text, language="en", max_chars=500: "Words can heal or hurt.",
    )
    explained = _wa_text(wa._build_reply(phone, "1"))
    assert "Words can heal or hurt" in explained
    assert "Pray with me" in explained

    # Menu number 2 from main opens Read My Bible, not the old help dump.
    update_user_session(phone, wa_flow="main")
    bible = _wa_text(wa._build_reply(phone, "2"))
    assert "Read My Bible" in bible
    assert "Old Testament" in bible
    assert "Send: VOTD" not in bible


def test_whatsapp_kids_votd_shows_niv_then_explanation(monkeypatch: Any) -> None:
    """Kids VOTD uses real NIV text, then meaning + example, with theme art."""

    from app.routes import whatsapp as wa

    phone = "+254700000211"
    clear_user_session(phone)
    update_user_session(
        phone,
        language_set=True,
        language="en",
        age_band="6_9",
        wa_flow="kids_hub",
    )
    monkeypatch.setattr(
        "app.services.kids_content.PUBLIC_BASE_URL",
        "https://example.test",
    )
    monkeypatch.setattr(
        wa,
        "get_verse_of_the_day_detail",
        lambda language="en", bible_id=None: {
            "passage_id": "PRO.18.21",
            "reference": "Proverbs 18:21",
            "text": (
                "The tongue has the power of life and death, "
                "and those who love it will eat its fruit."
            ),
        },
    )
    monkeypatch.setattr(wa, "prefer_bible_id", lambda *a, **k: 111)
    monkeypatch.setattr(
        wa,
        "list_bibles",
        lambda language, limit=5: [
            {"id": 111, "abbreviation": "NIV11", "title": "NIV 2011"}
        ],
    )
    monkeypatch.setattr(
        wa,
        "explain_votd_for_kid",
        lambda *a, **k: (
            "What it means:\n"
            "Your words can help or hurt.\n\n"
            "For example:\n"
            "Saying something kind can cheer up a friend."
        ),
    )

    reply = wa._build_reply(phone, "1")
    assert isinstance(reply, list)
    text = _wa_text(reply)
    assert "The tongue has the power of life and death" in text
    assert "What it means:" in text
    assert "For example:" in text
    assert "What you say can make someone feel happy" not in text
    image_parts = [p for p in reply if p.get("type") == "image"]
    assert image_parts
    assert "kind_words" in image_parts[0]["url"]


def test_whatsapp_kids_story_sends_visual(monkeypatch: Any) -> None:
    """Kids Corner stories on WhatsApp include a cover image + section text."""

    from app.routes import whatsapp as wa

    phone = "+254700000210"
    clear_user_session(phone)
    update_user_session(
        phone,
        language_set=True,
        language="en",
        age_band="6_9",
        wa_flow="kids_stories",
        kids_testament="old",
    )
    monkeypatch.setattr(
        wa, "PUBLIC_BASE_URL", "https://example.test", raising=False
    )
    monkeypatch.setattr(
        "app.services.kids_content.PUBLIC_BASE_URL",
        "https://example.test",
    )

    reply = wa._build_reply(phone, "1")  # Noah
    assert isinstance(reply, list)
    image_parts = [p for p in reply if p.get("type") == "image"]
    text_parts = [p for p in reply if p.get("type") == "text"]
    assert image_parts, "expected a story cover image"
    assert image_parts[0]["url"].endswith("/static/kids/noah.jpg")
    assert text_parts, "expected story section text"
    assert "Noah" in text_parts[0]["body"]
    assert "Got it" in text_parts[0]["body"]
    assert get_user_session(phone)["kids_story_id"] == "noah"
    assert get_user_session(phone)["wa_flow"] == "kids_got_it"


def test_ussd_first_request_welcomes_with_language_menu() -> None:
    """Ensure a brand-new phone gets welcome + language before the main menu."""

    phone = "+254700000001"
    clear_user_session(phone)
    response = client.post(
        "/ussd",
        data={
            "sessionId": "session-1",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "",
        },
    )

    assert response.status_code == 200
    assert response.text.startswith("CON ")
    assert "Welcome" in response.text
    assert "Choose language" in response.text
    assert "English" in response.text


def test_ussd_main_menu_after_language_set() -> None:
    """Ensure later dials skip straight to the main menu."""

    phone = "+254700000011"
    _onboard(phone)
    response = client.post(
        "/ussd",
        data={
            "sessionId": "session-main",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "",
        },
    )
    assert response.text.startswith("CON Scripture Without Screens")
    assert "2. Read My Bible" in response.text
    assert "3. Reading Plan" in response.text
    assert "4. Kids Corner" in response.text
    assert "6. Change Language" in response.text
    assert "0. Home" in response.text


def test_ussd_main_menu_follows_selected_language() -> None:
    """Ensure choosing Kiswahili localizes the whole main menu chrome."""

    phone = "+254700000012"
    _onboard(phone, language_choice="2")
    assert get_user_session(phone)["language"] == "sw"
    response = client.post(
        "/ussd",
        data={
            "sessionId": "session-main-sw",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "",
        },
    )
    assert "1. Aya ya Leo" in response.text
    assert "2. Soma Biblia Yangu" in response.text
    assert "3. Mpango wa Kusoma" in response.text
    assert "4. Konko ya Watoto" in response.text
    assert "6. Badilisha Lugha" in response.text
    assert "0. Nyumbani" in response.text
    assert "Change Language" not in response.text


def test_ussd_reading_plan_category_flow(monkeypatch: Any) -> None:
    """Ensure continue works and new plans browse category → plan → preview."""

    phone = "+254700000088"
    _onboard(phone)

    monkeypatch.setattr(
        "app.routes.ussd.get_passage",
        lambda reference, language="en", bible_id=None: f"Passage {reference}",
    )
    monkeypatch.setattr(
        "app.routes.ussd.get_passage_detail",
        lambda reference, language="en", bible_id=None: {
            "passage_id": reference,
            "reference": reference,
            "text": f"Passage {reference}",
        },
    )
    monkeypatch.setattr(
        "app.routes.ussd.translate_line",
        lambda text, language="en", age_band="6_9", max_chars=120: text,
    )

    client.post(
        "/ussd",
        data={
            "sessionId": "session-plan",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "",
        },
    )
    submenu = client.post(
        "/ussd",
        data={
            "sessionId": "session-plan",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "3",
        },
    )
    assert submenu.text.startswith("CON Reading Plan")
    assert "Continue current plan" in submenu.text
    assert "Start a new plan" in submenu.text

    day_one = client.post(
        "/ussd",
        data={
            "sessionId": "session-plan",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "3*1",
        },
    )
    assert day_one.text.startswith("CON ")
    assert "D1/" in day_one.text
    assert "Pray with me" in day_one.text
    assert get_user_session(phone)["plan_day"] == 2

    update_user_session(phone, ussd_flow="plan")
    topics = client.post(
        "/ussd",
        data={
            "sessionId": "session-plan-2",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "2",
        },
    )
    assert "Plan topic:" in topics.text
    assert "Wealth" in topics.text
    assert "Sadness" in topics.text

    # Wealth is category index 3 in CATEGORIES.
    wealth_plans = client.post(
        "/ussd",
        data={
            "sessionId": "session-plan-2",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "2*3",
        },
    )
    assert "Wealth plans:" in wealth_plans.text
    assert "True Riches" in wealth_plans.text

    preview = client.post(
        "/ussd",
        data={
            "sessionId": "session-plan-2",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "2*3*1",
        },
    )
    assert "True Riches" in preview.text
    assert "Start this plan" in preview.text
    assert "MAT.6.19-21" in preview.text or "D1" in preview.text

    started = client.post(
        "/ussd",
        data={
            "sessionId": "session-plan-2",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "2*3*1*1",
        },
    )
    assert started.text.startswith("CON ")
    assert "Pray with me" in started.text
    assert get_user_session(phone)["plan_id"] == "true-riches"
    # Day advanced after serving day 1.
    assert get_user_session(phone)["plan_day"] == 2


def test_ussd_votd_shows_citation_and_options(monkeypatch: Any) -> None:
    """Ensure VOTD includes reference, verse text, explain/pray/chapter options."""

    phone = "+254700000021"
    _onboard(phone)
    monkeypatch.setattr(
        "app.routes.ussd.get_verse_of_the_day_detail",
        lambda language="en", bible_id=None: {
            "passage_id": "JHN.3.16",
            "reference": "John 3:16",
            "text": "For God so loved the world.",
        },
    )
    monkeypatch.setattr(
        "app.routes.ussd.explain_scripture",
        lambda reference, text, language="en", max_chars=140: f"Meaning of {reference}",
    )
    monkeypatch.setattr(
        "app.routes.ussd.write_prayer",
        lambda reference, text, language="en", max_chars=140: f"Prayer from {reference}",
    )

    client.post(
        "/ussd",
        data={
            "sessionId": "session-2",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "",
        },
    )
    response = client.post(
        "/ussd",
        data={
            "sessionId": "session-2",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "1",
        },
    )

    assert response.status_code == 200
    assert response.text.startswith("CON ")
    assert "John 3:16" in response.text
    assert "For God so loved the world." in response.text
    assert "Explain this verse" in response.text
    assert "Pray with me" in response.text
    assert "Read full chapter" in response.text

    explained = client.post(
        "/ussd",
        data={
            "sessionId": "session-2",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "1*1",
        },
    )
    assert "Meaning of John 3:16" in explained.text


def test_ussd_read_my_bible_opens_ot_books(monkeypatch: Any) -> None:
    """Ensure Read My Bible lists Old Testament books from YouVersion."""

    phone = "+254700000031"
    _onboard(phone)
    monkeypatch.setattr(
        "app.routes.ussd.list_books",
        lambda language="en", bible_id=None, testament=None: [
            {
                "id": "GEN",
                "title": "Genesis",
                "canon": "old_testament",
                "chapter_count": 50,
            },
            {
                "id": "EXO",
                "title": "Exodus",
                "canon": "old_testament",
                "chapter_count": 40,
            },
        ],
    )

    client.post(
        "/ussd",
        data={
            "sessionId": "bible",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "",
        },
    )
    root = client.post(
        "/ussd",
        data={
            "sessionId": "bible",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "2",
        },
    )
    assert "Read My Bible" in root.text
    assert "Old Testament" in root.text

    books = client.post(
        "/ussd",
        data={
            "sessionId": "bible",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "2*1",
        },
    )
    assert "Old Testament books:" in books.text
    assert "Genesis" in books.text


def test_ussd_change_language_from_main_persists() -> None:
    """Ensure menu option 6 updates language without blocking on YouVersion."""

    phone = "+254700000099"
    _onboard(phone)
    client.post(
        "/ussd",
        data={
            "sessionId": "session-lang",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "",
        },
    )
    menu = client.post(
        "/ussd",
        data={
            "sessionId": "session-lang",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "6",
        },
    )
    assert "Choose language" in menu.text
    assert "Gĩkũyũ" in menu.text
    assert "Borana" in menu.text

    confirm = client.post(
        "/ussd",
        data={
            "sessionId": "session-lang",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "6*3",
        },
    )
    assert confirm.status_code == 200
    assert get_user_session(phone)["language"] == "ki"
    # Localized Kikuyu main menu returns in the same response (no YouVersion wait).
    assert "Ciugo cia" in confirm.text or "Garũra rũthiomi" in confirm.text


def test_ussd_kids_corner_section_and_home(monkeypatch: Any) -> None:
    """Ensure kids age → hub → OT stories → section → home."""

    phone = "+254700000077"
    _onboard(phone)
    monkeypatch.setattr(
        "app.routes.ussd.translate_line",
        lambda text, language="en", age_band="6_9", max_chars=120: text,
    )
    monkeypatch.setattr(
        "app.routes.ussd.simplify_for_kid",
        lambda text, language="en", age_band="6_9", max_chars=120: f"Simple: {text}",
    )

    client.post(
        "/ussd",
        data={
            "sessionId": "kids",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "",
        },
    )
    age = client.post(
        "/ussd",
        data={
            "sessionId": "kids",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "4",
        },
    )
    assert "your age" in age.text.lower() or "Kids Corner" in age.text

    hub = client.post(
        "/ussd",
        data={
            "sessionId": "kids",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "4*2",
        },
    )
    assert "Verse of the Day" in hub.text
    assert "Bible stories" in hub.text
    assert "Reading plans" in hub.text
    assert get_user_session(phone)["age_band"] == "6_9"

    testament = client.post(
        "/ussd",
        data={
            "sessionId": "kids",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "4*2*2",
        },
    )
    assert "Old Testament" in testament.text
    assert "New Testament" in testament.text

    stories = client.post(
        "/ussd",
        data={
            "sessionId": "kids",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "4*2*2*1",
        },
    )
    assert "Old Testament stories" in stories.text
    assert "Noah" in stories.text

    section = client.post(
        "/ussd",
        data={
            "sessionId": "kids",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "4*2*2*1*1",
        },
    )
    assert "Got it" in section.text
    assert "Explain simpler" in section.text
    assert get_user_session(phone)["kids_story_id"] == "noah"

    simpler = client.post(
        "/ussd",
        data={
            "sessionId": "kids",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "4*2*2*1*1*2",
        },
    )
    assert "Simple:" in simpler.text

    home = client.post(
        "/ussd",
        data={
            "sessionId": "kids",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "4*2*2*1*1*2*0",
        },
    )
    assert "Scripture Without Screens" in home.text
    assert get_user_session(phone)["ussd_flow"] == "main"


def test_ussd_kids_reading_plan_topics(monkeypatch: Any) -> None:
    """Ensure kids can open a topic reading plan day."""

    phone = "+254700000078"
    _onboard(phone)
    monkeypatch.setattr(
        "app.routes.ussd.translate_line",
        lambda text, language="en", age_band="6_9", max_chars=120: text,
    )
    update_user_session(
        phone, age_band="6_9", language_set=True, ussd_flow="kids_hub"
    )
    plans = client.post(
        "/ussd",
        data={
            "sessionId": "kplan",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "3",
        },
    )
    assert "Kindness" in plans.text
    assert "Christmas" in plans.text
    assert "Easter" in plans.text
    day = client.post(
        "/ussd",
        data={
            "sessionId": "kplan",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "3*1",
        },
    )
    assert "Kindness" in day.text
    assert "Next day" in day.text or "D1/" in day.text


def test_ussd_kids_quiz_accepts_correct_answer(monkeypatch: Any) -> None:
    """Ensure a correct quiz answer advances or finishes the kids story."""

    phone = "+254700000066"
    _onboard(phone)
    monkeypatch.setattr(
        "app.routes.ussd.translate_line",
        lambda text, language="en", age_band="6_9", max_chars=120: text,
    )
    update_user_session(
        phone,
        age_band="6_9",
        kids_story_id="noah",
        kids_section=2,
        kids_quiz_index=0,
        kids_quiz_retries=0,
        ussd_flow="kids_got_it",
        language_set=True,
    )
    # Got it on last section → quiz
    quiz = client.post(
        "/ussd",
        data={
            "sessionId": "quiz",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "1",
        },
    )
    assert "Quiz" in quiz.text
    assert get_user_session(phone)["ussd_flow"] == "kids_quiz"

    # Noah u6/6_9 first answer is 1 (Noah / God asked him)
    next_step = client.post(
        "/ussd",
        data={
            "sessionId": "quiz",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "1*1",
        },
    )
    assert next_step.status_code == 200
    assert (
        "Quiz" in next_step.text
        or "Pray" in next_step.text
        or "affirmation" in next_step.text.lower()
        or "finished" in next_step.text.lower()
        or "Yes!" in next_step.text
    )


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
    assert "STRESSED" in sent["message"]


def test_demo_sms_returns_reflection_body(monkeypatch: Any) -> None:
    """Ensure the SMS preview returns the message without sending."""

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


def test_sms_unknown_word_sends_usage_hint(monkeypatch: Any) -> None:
    """Ensure unsupported text receives a concise list of mood choices."""

    sent: dict[str, Any] = {}

    def fake_send_sms(
        message: str, recipient: str, sender_id: str | None = None
    ) -> dict[str, Any]:
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
    assert "STRESSED" in sent["message"]


def test_voice_first_callback_asks_for_language() -> None:
    """Ensure a new caller without language_set hears the language menu."""

    phone = "+254700000004"
    clear_user_session(phone)
    response = client.post(
        "/voice",
        data={
            "sessionId": "call-1",
            "callerNumber": phone,
            "destinationNumber": "+254711000000",
            "isActive": "1",
        },
    )

    root = fromstring(response.text)
    get_digits = root.find("GetDigits")

    assert response.status_code == 200
    assert get_digits is not None
    assert "language" in get_digits.findtext("Say", default="").lower()


def test_voice_option_one_reads_escaped_verse(monkeypatch: Any) -> None:
    """Ensure option 1 reads scripture and safely escapes XML characters."""

    phone = "+254700000044"
    clear_user_session(phone)
    update_user_session(
        phone, language_set=True, language="en", voice_flow="main"
    )
    monkeypatch.setattr(
        "app.routes.voice.get_verse_of_the_day",
        lambda language="en", bible_id=None: "Grace & peace are with you.",
    )
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
            "callerNumber": phone,
            "destinationNumber": "+254711000000",
            "isActive": "1",
            "dtmfDigits": "1",
        },
    )

    root = fromstring(response.text)

    assert response.status_code == 200
    assert root.findtext("Say") == "Grace & peace are with you."
    assert "&amp;" in response.text


def test_voice_kids_entry_asks_age(monkeypatch: Any) -> None:
    """Ensure voice Kids Corner prompts for age when unset."""

    phone = "+254700000055"
    clear_user_session(phone)
    update_user_session(
        phone, language_set=True, language="en", voice_flow="main"
    )
    response = client.post(
        "/voice",
        data={
            "sessionId": "call-kids",
            "callerNumber": phone,
            "destinationNumber": "+254711000000",
            "isActive": "1",
            "dtmfDigits": "3",
        },
    )
    root = fromstring(response.text)
    say = root.findtext(".//Say", default="")
    assert "Kids Corner" in say
    assert get_user_session(phone)["voice_flow"] == "kids_age"


def test_ussd_chapter_reading_offers_next_or_home(monkeypatch: Any) -> None:
    """Ensure whole-chapter reading offers next chapter vs Home."""

    phone = "+254700000013"
    _onboard(phone)
    update_user_session(
        phone,
        ussd_flow="bible_read",
        read_book="JHN",
        read_chapter=3,
        read_verse=1,
        language="en",
        language_set=True,
    )
    monkeypatch.setattr(
        "app.routes.ussd.get_book_chapter_count",
        lambda book, language="en", bible_id=None: 21,
    )

    def _fake_passage(passage_id, language="en", bible_id=None):
        return {
            "passage_id": passage_id,
            "reference": f"John {passage_id.split('.')[-1]}",
            "text": "For God so loved the world.",
        }

    monkeypatch.setattr("app.routes.ussd.get_passage_detail", _fake_passage)

    chapter_screen = client.post(
        "/ussd",
        data={
            "sessionId": "chapter-end",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "9",
        },
    )
    assert "John 3" in chapter_screen.text
    assert "1. Next chapter" in chapter_screen.text
    assert "0. Home" in chapter_screen.text

    next_chapter = client.post(
        "/ussd",
        data={
            "sessionId": "chapter-end",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "9*1",
        },
    )
    assert get_user_session(phone)["read_chapter"] == 4
    assert "John 4" in next_chapter.text


def test_ussd_version_menu_can_cancel(monkeypatch: Any) -> None:
    """Ensure version picker offers Cancel and restores prior bible_id."""

    phone = "+254700000014"
    _onboard(phone)
    update_user_session(phone, bible_id=12, ussd_flow="main")
    monkeypatch.setattr(
        "app.routes.ussd.list_bibles",
        lambda language="en", limit=5: [
            {"id": 99, "abbreviation": "NEN", "title": "Neno"},
            {"id": 12, "abbreviation": "ASV", "title": "ASV"},
        ],
    )
    client.post(
        "/ussd",
        data={
            "sessionId": "ver",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "",
        },
    )
    menu = client.post(
        "/ussd",
        data={
            "sessionId": "ver",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "5",
        },
    )
    assert "Choose Bible version" in menu.text
    assert "9. Cancel" in menu.text
    assert "0. Home" in menu.text

    cancelled = client.post(
        "/ussd",
        data={
            "sessionId": "ver",
            "phoneNumber": phone,
            "serviceCode": "*384*123#",
            "text": "5*9",
        },
    )
    assert "cancelled" in cancelled.text.lower()
    assert "Scripture Without Screens" in cancelled.text
    assert get_user_session(phone)["bible_id"] == 12
