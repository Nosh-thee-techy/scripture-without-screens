"""Africa's Talking inbound SMS webhook routes."""

from typing import Annotated

from fastapi import APIRouter, Form
from fastapi.responses import PlainTextResponse

from app.services.africastalking_client import (
    AfricasTalkingError,
    send_sms,
)
from app.services.gloo_client import generate_reflection
from app.services.youversion_client import YouVersionError, get_verse_of_the_day
from app.utils.formatters import format_for_sms


router = APIRouter(tags=["sms"])

SUPPORTED_MOODS = frozenset({"STRESSED", "GRATEFUL", "TIRED"})
MOOD_HELP_MESSAGE = "Reply STRESSED, GRATEFUL, or TIRED for a short reflection."
SCRIPTURE_ERROR_MESSAGE = (
    "Scripture is temporarily unavailable. Please try again later."
)


def _build_sms_reply(message: str) -> str:
    """Build an SMS reply from an inbound mood word.

    Args:
        message: Text received from the subscriber.

    Returns:
        A single-SMS reflection for a supported mood, a usage hint for other
        text, or a temporary error message when scripture retrieval fails.
    """

    mood = message.strip().upper()
    if mood not in SUPPORTED_MOODS:
        return MOOD_HELP_MESSAGE

    try:
        verse = get_verse_of_the_day()
    except YouVersionError:
        return SCRIPTURE_ERROR_MESSAGE

    reflection = generate_reflection(verse, mood=mood)
    return format_for_sms(reflection)


@router.post("/sms", response_class=PlainTextResponse)
def handle_inbound_sms(
    from_number: Annotated[str, Form(alias="from")],
    to_number: Annotated[str, Form(alias="to")],
    text: Annotated[str, Form()],
) -> PlainTextResponse:
    """Handle an inbound Africa's Talking SMS and send its reply.

    Args:
        from_number: Subscriber phone number that sent the message.
        to_number: Shortcode or phone number that received the message.
        text: Body of the inbound SMS.

    Returns:
        ``GOOD`` after the reply is submitted, or ``BAD`` with an error status
        if Africa's Talking cannot accept the outbound SMS.
    """

    reply = _build_sms_reply(text)
    try:
        # Reuse the receiving shortcode as the sender when it is configured for
        # two-way SMS, keeping the conversation on the same visible number.
        send_sms(reply, from_number, sender_id=to_number)
    except (AfricasTalkingError, ValueError):
        return PlainTextResponse("BAD", status_code=502)

    # Africa's Talking expects a plain acknowledgement rather than JSON.
    return PlainTextResponse("GOOD")
