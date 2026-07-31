"""Africa's Talking inbound voice webhook routes with Kids Corner."""

from typing import Annotated, Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import PlainTextResponse

from app.config import PUBLIC_BASE_URL
from app.services.africastalking_client import (
    build_voice_menu_response,
    build_voice_play_response,
    build_voice_say_response,
)
from app.services.elevenlabs_client import (
    ElevenLabsError,
    audio_public_path,
    synthesize_speech,
)
from app.services.kids_ai import simplify_for_kid, translate_line
from app.services.kids_content import (
    AGE_BANDS,
    get_quiz_questions,
    get_section,
    get_story,
    list_stories_for_age,
    section_count,
)
from app.services.reading_plan import get_plan_reference, next_plan_day
from app.services.youversion_client import (
    SUPPORTED_LANGUAGES,
    YouVersionError,
    get_passage,
    get_verse_of_the_day,
)
from app.utils.session_store import get_user_session, update_user_session


router = APIRouter(tags=["voice"])

VOICE_MENU = (
    "Welcome to Scripture Without Screens. "
    "Press 1 for the Verse of the Day. "
    "Press 2 to continue a reading plan. "
    "Press 3 for Kids Corner. "
    "Press 4 to hear your saved language. "
    "Press 5 to change language. "
    "Press 0 to hear this menu again."
)

VOICE_LANG_MENU = (
    "Welcome! Choose your language. "
    "Press 1 for English. "
    "Press 2 for Swahili. "
    "Press 3 for Kalenjin. "
    "Press 4 for Kikuyu. "
    "Press 5 for Dholuo."
)


def _voice_xml_response(xml: str) -> PlainTextResponse:
    """Return voice action XML with Africa's Talking's expected media type."""

    return PlainTextResponse(xml, media_type="text/plain")


def _public_base(request: Request) -> str:
    """Resolve the public base URL for Playable audio links."""

    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL
    return str(request.base_url).rstrip("/")


def _speak_message(
    request: Request, message: str, language: str, *, collect: bool = False
) -> PlainTextResponse:
    """Prefer ElevenLabs audio; fall back to Say. Optionally collect a digit."""

    if collect:
        # GetDigits must wrap spoken prompt; use Say path for reliable DTMF.
        return _voice_xml_response(build_voice_menu_response(message))

    try:
        audio_file = synthesize_speech(message, language_code=language)
        audio_url = f"{_public_base(request)}{audio_public_path(audio_file)}"
        return _voice_xml_response(build_voice_play_response(audio_url))
    except (ElevenLabsError, ValueError, OSError):
        return _voice_xml_response(build_voice_say_response(message))


def _set_voice(phone_number: str, flow: str, **fields: Any) -> dict[str, Any]:
    """Persist voice flow state."""

    return update_user_session(phone_number, voice_flow=flow, **fields)


def _kids_age_prompt() -> str:
    """Spoken age-band menu."""

    return (
        "Kids Corner. How old are you? "
        "Press 1 if under 6. "
        "Press 2 if ages 6 to 9. "
        "Press 3 if ages 10 to 12. "
        "Press 5 to change language. "
        "Press 0 for the main menu."
    )


def _kids_story_prompt(session: dict[str, Any]) -> str:
    """Spoken story picker."""

    age_band = str(session.get("age_band") or "6_9")
    stories = list_stories_for_age(age_band)
    parts = ["Kids stories."]
    offset = 1
    current_id = session.get("kids_story_id")
    if current_id:
        try:
            title = get_story(str(current_id))["title"]
            parts.append(f"Press 1 to continue {title}.")
            offset = 2
        except ValueError:
            pass
    for index, story in enumerate(stories, start=offset):
        parts.append(f"Press {index} for {story['title']}.")
    parts.append("Press 5 to change language. Press 0 for the main menu.")
    return " ".join(parts)


def _section_got_it_prompt(text: str) -> str:
    """Spoken section plus comprehension check."""

    return (
        f"{text} "
        "Press 1 if you got it. "
        "Press 2 for a simpler explanation. "
        "Press 5 to change language. "
        "Press 0 for the main menu."
    )


def _quiz_voice_prompt(session: dict[str, Any]) -> str:
    """Spoken quiz question."""

    story_id = str(session.get("kids_story_id") or "")
    age_band = str(session.get("age_band") or "6_9")
    index = int(session.get("kids_quiz_index") or 0)
    questions = get_quiz_questions(story_id, age_band)
    if index >= len(questions):
        return "Amazing! You finished the story. Goodbye for now."
    question = questions[index]
    parts = [f"Quiz question {index + 1}. {question['q']}"]
    for choice_index, choice in enumerate(question["choices"], start=1):
        parts.append(f"Press {choice_index} for {choice}.")
    parts.append("Press 5 to change language. Press 0 for the main menu.")
    return " ".join(parts)


def _advance_after_section(
    phone_number: str, session: dict[str, Any]
) -> tuple[str, bool]:
    """Move to the next section or start the quiz.

    Returns:
        ``(prompt, collect_digits)``.
    """

    story_id = str(session.get("kids_story_id") or "")
    section_index = int(session.get("kids_section") or 0)
    next_index = section_index + 1
    if next_index >= section_count(story_id):
        session = _set_voice(
            phone_number,
            "kids_quiz",
            kids_quiz_index=0,
            kids_quiz_retries=0,
        )
        return _quiz_voice_prompt(session), True
    session = _set_voice(phone_number, "kids_got_it", kids_section=next_index)
    return _speak_section(phone_number, session)


def _speak_section(
    phone_number: str, session: dict[str, Any]
) -> tuple[str, bool]:
    """Build the current section prompt in the child's language."""

    story_id = str(session.get("kids_story_id") or "")
    section_index = int(session.get("kids_section") or 0)
    age_band = str(session.get("age_band") or "6_9")
    language = str(session.get("language") or "en")
    english = get_section(story_id, section_index)
    display = translate_line(english, language=language, age_band=age_band)
    _set_voice(phone_number, "kids_got_it")
    return _section_got_it_prompt(display), True


def _handle_voice_digit(
    phone_number: str, digit: str
) -> tuple[str, str, bool]:
    """Resolve one DTMF digit against Redis voice_flow.

    Returns:
        ``(message, language, collect_more_digits)``.
    """

    session = get_user_session(phone_number)
    language = str(session.get("language") or "en")
    flow = str(session.get("voice_flow") or "boot")

    if not session.get("language_set") or flow == "lang":
        try:
            choice = int(digit)
        except ValueError:
            return VOICE_LANG_MENU, language, True
        if choice < 1 or choice > len(SUPPORTED_LANGUAGES):
            return VOICE_LANG_MENU, language, True
        code, label = SUPPORTED_LANGUAGES[choice - 1]
        _set_voice(
            phone_number,
            "main",
            language=code,
            language_set=True,
            bible_id=None,
        )
        return (
            f"Language set to {label}. {VOICE_MENU}",
            code,
            True,
        )

    if digit == "0":
        _set_voice(phone_number, "main")
        return VOICE_MENU, language, True

    if digit == "5" and flow != "main":
        _set_voice(phone_number, "lang")
        return VOICE_LANG_MENU, language, True

    if flow == "main":
        if digit == "1":
            try:
                verse = get_verse_of_the_day(
                    language=language, bible_id=session.get("bible_id")
                )
            except YouVersionError:
                verse = (
                    "Scripture is temporarily unavailable. Please call again later."
                )
            return verse, language, False
        if digit == "2":
            plan_id = str(session.get("plan_id") or "hope-kenya")
            day_number = int(session.get("plan_day") or 1)
            try:
                reference = get_plan_reference(plan_id, day_number)
                passage = get_passage(
                    reference, language=language, bible_id=session.get("bible_id")
                )
            except (ValueError, YouVersionError):
                return (
                    "Reading plan is temporarily unavailable. Please try later.",
                    language,
                    False,
                )
            update_user_session(
                phone_number, plan_day=next_plan_day(plan_id, day_number)
            )
            return f"Day {day_number}. {passage}", language, False
        if digit == "3":
            if not session.get("age_band"):
                _set_voice(phone_number, "kids_age")
                return _kids_age_prompt(), language, True
            _set_voice(phone_number, "kids_stories")
            return _kids_story_prompt(get_user_session(phone_number)), language, True
        if digit == "4":
            return (
                f"Your saved language code is {language}. "
                "Press 5 to change it, or 0 for the main menu.",
                language,
                True,
            )
        if digit == "5":
            _set_voice(phone_number, "lang")
            return VOICE_LANG_MENU, language, True
        return VOICE_MENU, language, True

    if flow == "kids_age":
        try:
            choice = int(digit)
        except ValueError:
            return _kids_age_prompt(), language, True
        if choice < 1 or choice > len(AGE_BANDS):
            return _kids_age_prompt(), language, True
        age_code, _label = AGE_BANDS[choice - 1]
        session = _set_voice(phone_number, "kids_stories", age_band=age_code)
        return _kids_story_prompt(session), language, True

    if flow == "kids_stories":
        age_band = str(session.get("age_band") or "6_9")
        stories = list_stories_for_age(age_band)
        current_id = session.get("kids_story_id")
        try:
            choice = int(digit)
        except ValueError:
            return _kids_story_prompt(session), language, True
        if current_id and choice == 1:
            prompt, collect = _speak_section(phone_number, session)
            return prompt, language, collect
        story_index = choice - 2 if current_id else choice - 1
        if story_index < 0 or story_index >= len(stories):
            return _kids_story_prompt(session), language, True
        story = stories[story_index]
        session = _set_voice(
            phone_number,
            "kids_got_it",
            kids_story_id=story["id"],
            kids_section=0,
            kids_quiz_index=0,
            kids_quiz_retries=0,
        )
        prompt, collect = _speak_section(phone_number, session)
        return prompt, language, collect

    if flow == "kids_got_it":
        if digit == "2":
            story_id = str(session.get("kids_story_id") or "")
            section_index = int(session.get("kids_section") or 0)
            age_band = str(session.get("age_band") or "6_9")
            english = get_section(story_id, section_index)
            simpler = simplify_for_kid(
                english, language=language, age_band=age_band
            )
            return _section_got_it_prompt(simpler), language, True
        if digit == "1":
            prompt, collect = _advance_after_section(phone_number, session)
            return prompt, language, collect
        prompt, collect = _speak_section(phone_number, session)
        return prompt, language, collect

    if flow == "kids_quiz":
        story_id = str(session.get("kids_story_id") or "")
        age_band = str(session.get("age_band") or "6_9")
        index = int(session.get("kids_quiz_index") or 0)
        retries = int(session.get("kids_quiz_retries") or 0)
        questions = get_quiz_questions(story_id, age_band)
        if index >= len(questions):
            _set_voice(phone_number, "main")
            return "You finished the quiz. Well done!", language, False
        question = questions[index]
        try:
            choice = int(digit)
        except ValueError:
            return _quiz_voice_prompt(session), language, True
        if choice < 1 or choice > len(question["choices"]):
            return _quiz_voice_prompt(session), language, True
        if choice == int(question["answer"]):
            next_q = index + 1
            if next_q >= len(questions):
                _set_voice(
                    phone_number,
                    "main",
                    kids_section=0,
                    kids_quiz_index=0,
                    kids_quiz_retries=0,
                )
                return (
                    "Yes! You finished the kids quiz. You were wonderful. Goodbye!",
                    language,
                    False,
                )
            session = _set_voice(
                phone_number,
                "kids_quiz",
                kids_quiz_index=next_q,
                kids_quiz_retries=0,
            )
            return (
                f"Correct! {_quiz_voice_prompt(session)}",
                language,
                True,
            )
        if retries < 1:
            _set_voice(phone_number, "kids_quiz", kids_quiz_retries=retries + 1)
            hint = question.get("hint") or "Try once more."
            return (
                f"Almost! {hint} {_quiz_voice_prompt(get_user_session(phone_number))}",
                language,
                True,
            )
        correct = question["choices"][int(question["answer"]) - 1]
        next_q = index + 1
        if next_q >= len(questions):
            _set_voice(phone_number, "main")
            return (
                f"The answer was {correct}. Story complete. Goodbye!",
                language,
                False,
            )
        session = _set_voice(
            phone_number,
            "kids_quiz",
            kids_quiz_index=next_q,
            kids_quiz_retries=0,
        )
        return (
            f"The answer was {correct}. {_quiz_voice_prompt(session)}",
            language,
            True,
        )

    _set_voice(phone_number, "main")
    return VOICE_MENU, language, True


@router.post("/voice", response_class=PlainTextResponse)
def handle_voice_call(
    request: Request,
    session_id: Annotated[str, Form(alias="sessionId")],
    caller_number: Annotated[str, Form(alias="callerNumber")],
    destination_number: Annotated[str, Form(alias="destinationNumber")],
    is_active: Annotated[str, Form(alias="isActive")] = "1",
    dtmf_digits: Annotated[str | None, Form(alias="dtmfDigits")] = None,
) -> PlainTextResponse:
    """Handle an Africa's Talking call instruction callback."""

    _ = session_id, destination_number

    if is_active.strip().lower() in {"0", "false"}:
        return PlainTextResponse("")

    session = get_user_session(caller_number)
    language = str(session.get("language") or "en")

    if not dtmf_digits:
        if not session.get("language_set"):
            _set_voice(caller_number, "lang")
            return _speak_message(
                request, VOICE_LANG_MENU, language, collect=True
            )
        _set_voice(caller_number, "main")
        return _speak_message(request, VOICE_MENU, language, collect=True)

    message, language, collect = _handle_voice_digit(
        caller_number, dtmf_digits.strip()
    )
    return _speak_message(request, message, language, collect=collect)
