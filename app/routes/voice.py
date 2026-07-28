"""Africa's Talking inbound voice webhook routes."""

from typing import Annotated

from fastapi import APIRouter, Form
from fastapi.responses import PlainTextResponse

from app.services.africastalking_client import (
    build_voice_menu_response,
    build_voice_say_response,
)
from app.services.youversion_client import YouVersionError, get_verse_of_the_day


router = APIRouter(tags=["voice"])

VOICE_MENU = (
    "Welcome to Scripture Without Screens. "
    "Press 1 for the Verse of the Day. "
    "Press 2 to continue a reading plan. "
    "Press 3 to change language."
)


def _voice_xml_response(xml: str) -> PlainTextResponse:
    """Return voice action XML with Africa's Talking's expected media type.

    Args:
        xml: Complete Africa's Talking ``Response`` XML document.

    Returns:
        A plain-text HTTP response containing the XML instructions.
    """

    return PlainTextResponse(xml, media_type="text/plain")


def _message_for_digits(dtmf_digits: str) -> str:
    """Resolve a keypad selection to the message that should be spoken.

    Args:
        dtmf_digits: Digits collected by Africa's Talking ``GetDigits``.

    Returns:
        Scripture for option 1 or a short status message for other selections.
    """

    selection = dtmf_digits.strip()
    if selection == "1":
        try:
            return get_verse_of_the_day()
        except YouVersionError:
            return "Scripture is temporarily unavailable. Please call again later."
    if selection == "2":
        return "Reading plans are coming soon. Goodbye."
    if selection == "3":
        return "Language selection is coming soon. Goodbye."
    return "That was not a valid choice. Please call again. Goodbye."


@router.post("/voice", response_class=PlainTextResponse)
def handle_voice_call(
    session_id: Annotated[str, Form(alias="sessionId")],
    caller_number: Annotated[str, Form(alias="callerNumber")],
    destination_number: Annotated[str, Form(alias="destinationNumber")],
    is_active: Annotated[str, Form(alias="isActive")] = "1",
    dtmf_digits: Annotated[str | None, Form(alias="dtmfDigits")] = None,
) -> PlainTextResponse:
    """Handle an Africa's Talking call instruction callback.

    Args:
        session_id: Africa's Talking identifier for this call.
        caller_number: Phone number that initiated the call.
        destination_number: Africa's Talking number that received the call.
        is_active: Gateway flag indicating whether the call is still active.
        dtmf_digits: Optional keypad selection from an earlier ``GetDigits``.

    Returns:
        Voice action XML for active calls, or an empty acknowledgement after
        the call has ended.
    """

    # Completion callbacks contain billing/duration fields and do not expect
    # more call instructions.
    if is_active.strip().lower() in {"0", "false"}:
        return PlainTextResponse("")

    # Africa's Talking sends collected digits back to the number's configured
    # callback URL when GetDigits has no explicit callbackUrl.
    if not dtmf_digits:
        return _voice_xml_response(build_voice_menu_response(VOICE_MENU))

    message = _message_for_digits(dtmf_digits)
    return _voice_xml_response(build_voice_say_response(message))
