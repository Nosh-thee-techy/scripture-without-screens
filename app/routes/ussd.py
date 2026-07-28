"""Africa's Talking USSD webhook routes."""

from typing import Annotated

from fastapi import APIRouter, Form
from fastapi.responses import PlainTextResponse

from app.services.youversion_client import YouVersionError, get_verse_of_the_day
from app.utils.formatters import format_for_ussd


router = APIRouter(tags=["ussd"])

MAIN_MENU = (
    "Scripture Without Screens\n"
    "1. Verse of the Day\n"
    "2. Continue Reading Plan\n"
    "3. Change Language"
)
def _parse_selections(text: str) -> list[str]:
    """Split Africa's Talking cumulative menu text into user selections.

    Args:
        text: Asterisk-delimited input received from the USSD webhook.

    Returns:
        A list containing each non-empty menu selection in order.
    """

    return [selection.strip() for selection in text.split("*") if selection.strip()]


def _ussd_response(status: str, message: str) -> PlainTextResponse:
    """Build a plain-text response using Africa's Talking control prefixes.

    Args:
        status: Either ``"CON"`` to continue or ``"END"`` to close the session.
        message: Text to display on the subscriber's phone.

    Returns:
        A plain-text HTTP response accepted by Africa's Talking.
    """

    return PlainTextResponse(f"{status} {message}")


@router.post("/ussd", response_class=PlainTextResponse)
def handle_ussd(
    session_id: Annotated[str, Form(alias="sessionId")],
    phone_number: Annotated[str, Form(alias="phoneNumber")],
    service_code: Annotated[str, Form(alias="serviceCode")],
    text: Annotated[str, Form()],
) -> PlainTextResponse:
    """Handle one Africa's Talking USSD callback.

    Args:
        session_id: Africa's Talking identifier for the active USSD session.
        phone_number: Subscriber phone number associated with the session.
        service_code: USSD code the subscriber dialed.
        text: Cumulative asterisk-delimited menu input; empty on first contact.

    Returns:
        A ``CON`` response for the main menu or an ``END`` response containing
        the selected result or a clear error message.
    """

    # Africa's Talking sends the full input path on every callback (for example
    # "3*1"), so this first menu can be reconstructed without server-side state.
    # session_id and phone_number will become useful when plan/language state is
    # added to session_store.py.
    selections = _parse_selections(text)

    if not selections:
        return _ussd_response("CON", MAIN_MENU)

    if selections == ["1"]:
        try:
            verse = get_verse_of_the_day()
        except YouVersionError:
            return _ussd_response(
                "END", "Scripture is temporarily unavailable. Please try again."
            )
        return _ussd_response("END", format_for_ussd(verse))

    if selections[0] in {"2", "3"}:
        return _ussd_response("END", "This option is coming soon.")

    return _ussd_response("END", "Invalid choice. Please dial again.")
