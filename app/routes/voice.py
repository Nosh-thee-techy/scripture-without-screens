"""Africa's Talking inbound voice webhook routes."""

from typing import Annotated

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
from app.services.reading_plan import get_plan_reference, next_plan_day
from app.services.youversion_client import (
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
    "Press 3 to hear your saved language. "
    "Use USSD to change language or Bible version."
)


def _voice_xml_response(xml: str) -> PlainTextResponse:
    """Return voice action XML with Africa's Talking's expected media type.

    Args:
        xml: Complete Africa's Talking ``Response`` XML document.

    Returns:
        A plain-text HTTP response containing the XML instructions.
    """

    return PlainTextResponse(xml, media_type="text/plain")


def _public_base(request: Request) -> str:
    """Resolve the public base URL for Playable audio links.

    Args:
        request: Incoming FastAPI request (used when PUBLIC_BASE_URL is unset).

    Returns:
        An absolute origin such as ``https://....ngrok-free.dev``.
    """

    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL
    return str(request.base_url).rstrip("/")


def _speak_message(
    request: Request, message: str, language: str
) -> PlainTextResponse:
    """Prefer ElevenLabs audio via Play; fall back to Africa's Talking Say.

    Args:
        request: Incoming request used to build absolute audio URLs.
        message: Scripture or status text to speak.
        language: Session language code for TTS hints.

    Returns:
        Voice action XML using ``Play`` or ``Say``.
    """

    try:
        audio_file = synthesize_speech(message, language_code=language)
        audio_url = f"{_public_base(request)}{audio_public_path(audio_file)}"
        return _voice_xml_response(build_voice_play_response(audio_url))
    except (ElevenLabsError, ValueError, OSError):
        return _voice_xml_response(build_voice_say_response(message))


def _message_for_digits(dtmf_digits: str, phone_number: str) -> tuple[str, str]:
    """Resolve a keypad selection using Redis preferences for the caller.

    Args:
        dtmf_digits: Digits collected by Africa's Talking ``GetDigits``.
        phone_number: Caller MSISDN used as the Redis session key.

    Returns:
        A ``(message, language)`` pair for speech synthesis.
    """

    session = get_user_session(phone_number)
    language = str(session.get("language") or "en")
    bible_id = session.get("bible_id")
    selection = dtmf_digits.strip()

    if selection == "1":
        try:
            return (
                get_verse_of_the_day(language=language, bible_id=bible_id),
                language,
            )
        except YouVersionError:
            return (
                "Scripture is temporarily unavailable. Please call again later.",
                language,
            )

    if selection == "2":
        plan_id = str(session.get("plan_id") or "hope-kenya")
        day_number = int(session.get("plan_day") or 1)
        try:
            reference = get_plan_reference(plan_id, day_number)
            passage = get_passage(
                reference, language=language, bible_id=bible_id
            )
        except (ValueError, YouVersionError):
            return (
                "Reading plan is temporarily unavailable. Please try later.",
                language,
            )
        update_user_session(
            phone_number, plan_day=next_plan_day(plan_id, day_number)
        )
        return f"Day {day_number}. {passage}", language

    if selection == "3":
        return (
            f"Your saved language code is {language}. "
            "Dial the USSD code to change language or Bible version.",
            language,
        )

    return "That was not a valid choice. Please call again. Goodbye.", language


@router.post("/voice", response_class=PlainTextResponse)
def handle_voice_call(
    request: Request,
    session_id: Annotated[str, Form(alias="sessionId")],
    caller_number: Annotated[str, Form(alias="callerNumber")],
    destination_number: Annotated[str, Form(alias="destinationNumber")],
    is_active: Annotated[str, Form(alias="isActive")] = "1",
    dtmf_digits: Annotated[str | None, Form(alias="dtmfDigits")] = None,
) -> PlainTextResponse:
    """Handle an Africa's Talking call instruction callback.

    Args:
        request: FastAPI request (for public audio URL construction).
        session_id: Africa's Talking identifier for this call.
        caller_number: Phone number that initiated the call.
        destination_number: Africa's Talking number that received the call.
        is_active: Gateway flag indicating whether the call is still active.
        dtmf_digits: Optional keypad selection from an earlier ``GetDigits``.

    Returns:
        Voice action XML for active calls, or an empty acknowledgement after
        the call has ended.
    """

    _ = session_id, destination_number

    # Completion callbacks contain billing/duration fields and do not expect
    # more call instructions.
    if is_active.strip().lower() in {"0", "false"}:
        return PlainTextResponse("")

    # Africa's Talking sends collected digits back to the number's configured
    # callback URL when GetDigits has no explicit callbackUrl.
    if not dtmf_digits:
        return _voice_xml_response(build_voice_menu_response(VOICE_MENU))

    message, language = _message_for_digits(dtmf_digits, caller_number)
    return _speak_message(request, message, language)
