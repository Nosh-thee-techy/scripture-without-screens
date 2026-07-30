"""Africa's Talking USSD webhook routes with Redis-backed preferences."""

from typing import Annotated, Any

from fastapi import APIRouter, Form
from fastapi.responses import PlainTextResponse

from app.services.reading_plan import (
    get_plan_reference,
    list_plans,
    next_plan_day,
    plan_label,
)
from app.services.youversion_client import (
    SUPPORTED_LANGUAGES,
    YouVersionError,
    YouVersionNotFoundError,
    get_passage,
    get_verse_of_the_day,
    list_bibles,
)
from app.utils.formatters import format_for_ussd
from app.utils.session_store import get_user_session, update_user_session


router = APIRouter(tags=["ussd"])

MAIN_MENU = (
    "Scripture Without Screens\n"
    "1. Verse of the Day\n"
    "2. Reading Plan\n"
    "3. Change Language\n"
    "4. Change Bible Version"
)

READING_PLAN_MENU = (
    "Reading Plan\n"
    "1. Continue today\n"
    "2. Choose a plan\n"
    "3. Restart current"
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


def _language_menu() -> str:
    """Build the Change Language USSD submenu.

    Returns:
        A numbered list of supported language labels.
    """

    lines = ["Choose language:"]
    for index, (_code, label) in enumerate(SUPPORTED_LANGUAGES, start=1):
        lines.append(f"{index}. {label}")
    return "\n".join(lines)


def _version_menu(bibles: list[dict[str, Any]]) -> str:
    """Build the Change Bible Version USSD submenu.

    Args:
        bibles: Version dictionaries from ``list_bibles``.

    Returns:
        A numbered list of short Bible abbreviations.
    """

    lines = ["Choose Bible version:"]
    for index, bible in enumerate(bibles, start=1):
        lines.append(f"{index}. {bible['abbreviation']}")
    return "\n".join(lines)


def _plan_choice_menu() -> str:
    """Build the Choose a plan USSD submenu.

    Returns:
        A numbered list of local reading plans with day counts.
    """

    lines = ["Choose plan:"]
    for index, (_plan_id, label, days) in enumerate(list_plans(), start=1):
        lines.append(f"{index}. {label} ({days}d)")
    return "\n".join(lines)


def _handle_verse_of_the_day(session: dict[str, Any]) -> PlainTextResponse:
    """Fetch and display today's verse using the subscriber's preferences.

    Args:
        session: Redis-backed preference document for the caller.

    Returns:
        An ``END`` response containing truncated verse text or an error.
    """

    try:
        verse = get_verse_of_the_day(
            language=str(session.get("language") or "en"),
            bible_id=session.get("bible_id"),
        )
    except YouVersionError:
        return _ussd_response(
            "END",
            "Scripture unavailable. Check YOUVERSION_API_KEY / licenses.",
        )
    return _ussd_response("END", format_for_ussd(verse))


def _serve_plan_day(
    phone_number: str, session: dict[str, Any]
) -> PlainTextResponse:
    """Serve today's local plan passage and advance the saved day.

    Args:
        phone_number: Subscriber MSISDN used as the Redis session key.
        session: Current preference document.

    Returns:
        An ``END`` response with the day's passage or an error message.
    """

    plan_id = str(session.get("plan_id") or "hope-kenya")
    day_number = int(session.get("plan_day") or 1)

    try:
        reference = get_plan_reference(plan_id, day_number)
        passage = get_passage(
            reference,
            language=str(session.get("language") or "en"),
            bible_id=session.get("bible_id"),
        )
    except (ValueError, YouVersionError):
        return _ussd_response(
            "END",
            "Reading plan unavailable. Check API key and Bible licenses.",
        )

    update_user_session(
        phone_number,
        plan_day=next_plan_day(plan_id, day_number),
    )
    label = plan_label(plan_id)
    body = format_for_ussd(f"{label} D{day_number}: {passage}")
    return _ussd_response("END", body)


def _handle_reading_plan(
    phone_number: str, session: dict[str, Any], selections: list[str]
) -> PlainTextResponse:
    """Show the reading-plan submenu or apply continue / choose / restart.

    Args:
        phone_number: Subscriber MSISDN.
        session: Current preference document.
        selections: Cumulative USSD path starting with ``"2"``.

    Returns:
        A ``CON`` submenu or an ``END`` confirmation / passage.
    """

    if len(selections) == 1:
        current = plan_label(str(session.get("plan_id") or "hope-kenya"))
        day = int(session.get("plan_day") or 1)
        return _ussd_response(
            "CON",
            f"{READING_PLAN_MENU}\nNow: {current} day {day}",
        )

    action = selections[1]

    if action == "1":
        return _serve_plan_day(phone_number, session)

    if action == "3":
        update_user_session(phone_number, plan_day=1)
        label = plan_label(str(session.get("plan_id") or "hope-kenya"))
        return _ussd_response("END", f"{label} restarted at day 1.")

    if action == "2":
        if len(selections) == 2:
            return _ussd_response("CON", _plan_choice_menu())

        try:
            choice = int(selections[2])
        except ValueError:
            return _ussd_response("END", "Invalid plan. Dial again.")

        plans = list_plans()
        if choice < 1 or choice > len(plans):
            return _ussd_response("END", "Invalid plan. Dial again.")

        plan_id, label, _days = plans[choice - 1]
        update_user_session(phone_number, plan_id=plan_id, plan_day=1)
        return _ussd_response(
            "END",
            f"Plan set to {label}. Dial 2 then 1 for day 1.",
        )

    return _ussd_response("END", "Invalid choice. Dial again.")


def _handle_change_language(
    phone_number: str, selections: list[str]
) -> PlainTextResponse:
    """Show or apply a language choice and clear a stale Bible version.

    Args:
        phone_number: Subscriber MSISDN.
        selections: Cumulative USSD path starting with ``"3"``.

    Returns:
        A ``CON`` language menu or an ``END`` confirmation.
    """

    if len(selections) == 1:
        return _ussd_response("CON", _language_menu())

    try:
        choice = int(selections[1])
    except ValueError:
        return _ussd_response("END", "Invalid language. Dial again.")

    if choice < 1 or choice > len(SUPPORTED_LANGUAGES):
        return _ussd_response("END", "Invalid language. Dial again.")

    language_code, language_label = SUPPORTED_LANGUAGES[choice - 1]
    # Reset bible_id so the next fetch picks a version licensed for the new
    # language instead of reusing an English ID after switching to Kalenjin.
    update_user_session(
        phone_number,
        language=language_code,
        bible_id=None,
    )
    return _ussd_response(
        "END",
        f"Language set to {language_label}. Use 4 to pick a Bible version.",
    )


def _handle_change_version(
    phone_number: str, session: dict[str, Any], selections: list[str]
) -> PlainTextResponse:
    """Show or apply a Bible version licensed for the saved language.

    Args:
        phone_number: Subscriber MSISDN.
        session: Current preference document.
        selections: Cumulative USSD path starting with ``"4"``.

    Returns:
        A ``CON`` version menu or an ``END`` confirmation / error.
    """

    language = str(session.get("language") or "en")
    try:
        bibles = list_bibles(language, limit=5)
    except YouVersionNotFoundError:
        return _ussd_response(
            "END",
            "No Bible licensed for this language in YouVersion yet.",
        )
    except YouVersionError:
        return _ussd_response(
            "END",
            "Could not load versions. Check YOUVERSION_API_KEY.",
        )

    if len(selections) == 1:
        return _ussd_response("CON", _version_menu(bibles))

    try:
        choice = int(selections[1])
    except ValueError:
        return _ussd_response("END", "Invalid version. Dial again.")

    if choice < 1 or choice > len(bibles):
        return _ussd_response("END", "Invalid version. Dial again.")

    selected = bibles[choice - 1]
    update_user_session(phone_number, bible_id=selected["id"])
    return _ussd_response(
        "END",
        f"Bible set to {selected['abbreviation']}.",
    )


@router.post("/ussd", response_class=PlainTextResponse)
def handle_ussd(
    session_id: Annotated[str, Form(alias="sessionId")],
    phone_number: Annotated[str, Form(alias="phoneNumber")],
    service_code: Annotated[str, Form(alias="serviceCode")],
    text: Annotated[str, Form()],
) -> PlainTextResponse:
    """Handle one Africa's Talking USSD callback.

    Preferences are loaded from Redis by ``phone_number`` so language, Bible
    version, and reading-plan day persist across dials. ``session_id`` identifies
    the live USSD transaction from Africa's Talking.

    Args:
        session_id: Africa's Talking identifier for the active USSD session.
        phone_number: Subscriber phone number associated with the session.
        service_code: USSD code the subscriber dialed.
        text: Cumulative asterisk-delimited menu input; empty on first contact.

    Returns:
        A ``CON`` or ``END`` plain-text response for Africa's Talking.
    """

    _ = session_id, service_code
    session = get_user_session(phone_number)
    selections = _parse_selections(text)

    if not selections:
        return _ussd_response("CON", MAIN_MENU)

    choice = selections[0]
    if choice == "1":
        return _handle_verse_of_the_day(session)
    if choice == "2":
        return _handle_reading_plan(phone_number, session, selections)
    if choice == "3":
        return _handle_change_language(phone_number, selections)
    if choice == "4":
        return _handle_change_version(phone_number, session, selections)

    return _ussd_response("END", "Invalid choice. Please dial again.")
