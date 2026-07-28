"""Small, synchronous client for scripture data from YouVersion Platform."""

from datetime import datetime, timezone
from typing import Any

import requests

from app.config import (
    YOUVERSION_API_KEY,
    YOUVERSION_BASE_URL,
    YOUVERSION_TIMEOUT_SECONDS,
)


class YouVersionError(RuntimeError):
    """Base exception for recoverable YouVersion client failures."""


class YouVersionNotFoundError(YouVersionError):
    """Raised when YouVersion cannot find the requested content."""


class YouVersionUnsupportedError(YouVersionError):
    """Raised when the public Platform API does not expose requested content."""


def _normalise_language(language: str) -> str:
    """Convert a supported language code to the BCP 47 form used by YouVersion.

    Args:
        language: An ISO 639 language code, such as ``"eng"`` or ``"en"``.

    Returns:
        A BCP 47-compatible language range.
    """

    aliases = {"eng": "en"}
    cleaned_language = language.strip().lower()
    return aliases.get(cleaned_language, cleaned_language)


def _request_json(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Send an authenticated GET request and return its JSON object.

    Args:
        path: API path relative to the configured YouVersion base URL.
        params: Optional query-string parameters.

    Returns:
        The decoded JSON response object.

    Raises:
        YouVersionNotFoundError: If the requested resource does not exist.
        YouVersionError: If configuration, networking, HTTP, or JSON decoding
            fails.
    """

    if not YOUVERSION_API_KEY:
        raise YouVersionError(
            "YOUVERSION_API_KEY is not configured. Add it to the environment "
            "or a local .env file."
        )

    try:
        response = requests.get(
            f"{YOUVERSION_BASE_URL}/{path.lstrip('/')}",
            headers={"X-YVP-App-Key": YOUVERSION_API_KEY},
            params=params,
            timeout=YOUVERSION_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise YouVersionError("Could not connect to YouVersion.") from exc

    if response.status_code == 404:
        raise YouVersionNotFoundError(
            "YouVersion could not find the requested content."
        )

    try:
        response.raise_for_status()
        payload = response.json()
    except requests.HTTPError as exc:
        raise YouVersionError(
            f"YouVersion returned HTTP {response.status_code}."
        ) from exc
    except requests.JSONDecodeError as exc:
        raise YouVersionError("YouVersion returned invalid JSON.") from exc

    if not isinstance(payload, dict):
        raise YouVersionError("YouVersion returned an unexpected response.")
    return payload


def _get_bible_id(language: str) -> int:
    """Find the first Bible version licensed for the requested language.

    Args:
        language: An ISO 639 or BCP 47 language code.

    Returns:
        The numeric ID of an available Bible version.

    Raises:
        YouVersionNotFoundError: If no licensed Bible is available.
        YouVersionError: If YouVersion returns malformed version data.
    """

    language_range = _normalise_language(language)
    payload = _request_json(
        "bibles",
        params={"language_ranges[]": language_range, "page_size": 1},
    )
    bibles = payload.get("data")
    if not isinstance(bibles, list) or not bibles:
        raise YouVersionNotFoundError(
            f"No licensed Bible version is available for '{language}'."
        )

    bible_id = bibles[0].get("id") if isinstance(bibles[0], dict) else None
    if not isinstance(bible_id, int):
        raise YouVersionError("YouVersion returned an invalid Bible version.")
    return bible_id


def _extract_content(payload: dict[str, Any]) -> str:
    """Extract and normalize plain scripture text from an API response.

    Args:
        payload: A decoded YouVersion passage response.

    Returns:
        Plain text with repeated whitespace collapsed for phone delivery.

    Raises:
        YouVersionNotFoundError: If the response contains no passage text.
    """

    content = payload.get("content")
    if not isinstance(content, str) or not content.strip():
        raise YouVersionNotFoundError(
            "YouVersion returned no text for the requested passage."
        )

    # Text responses can contain line breaks and indentation that waste limited
    # USSD/SMS space, so collapse all whitespace without truncating scripture.
    return " ".join(content.split())


def get_verse_of_the_day(language: str = "eng") -> str:
    """Return today's curated YouVersion verse as plain text.

    Args:
        language: ISO 639 or BCP 47 code for the desired Bible language.

    Returns:
        Today's verse text in the first licensed version for the language.

    Raises:
        YouVersionNotFoundError: If today's verse or a translation is missing.
        YouVersionError: If the API request or response is invalid.
    """

    day_of_year = datetime.now(timezone.utc).timetuple().tm_yday
    verse = _request_json(f"verse_of_the_days/{day_of_year}")
    passage_id = verse.get("passage_id")
    if not isinstance(passage_id, str) or not passage_id.strip():
        raise YouVersionNotFoundError(
            "YouVersion did not provide a Verse of the Day reference."
        )
    return get_passage(passage_id, language)


def get_passage(reference: str, language: str = "eng") -> str:
    """Return a Bible passage as plain text.

    Args:
        reference: A USFM passage ID, for example ``"JHN.3.16"``.
        language: ISO 639 or BCP 47 code for the desired Bible language.

    Returns:
        Plain passage text in the first licensed version for the language.

    Raises:
        ValueError: If ``reference`` is blank.
        YouVersionNotFoundError: If no matching passage or translation exists.
        YouVersionError: If the API request or response is invalid.
    """

    cleaned_reference = reference.strip()
    if not cleaned_reference:
        raise ValueError("reference must not be blank")

    bible_id = _get_bible_id(language)
    payload = _request_json(
        f"bibles/{bible_id}/passages/{cleaned_reference}",
        params={"format": "text"},
    )
    return _extract_content(payload)


def get_reading_plan_day(plan_id: str, day_number: int) -> str:
    """Report that reading-plan content is unavailable in Platform API v1.

    Args:
        plan_id: Identifier of the desired YouVersion reading plan.
        day_number: One-based day number within that plan.

    Returns:
        This function does not return while the public API lacks plan content.

    Raises:
        ValueError: If ``plan_id`` is blank or ``day_number`` is below one.
        YouVersionUnsupportedError: Always, because the current public
            YouVersion Platform API has no reading-plan content endpoint.
    """

    if not plan_id.strip():
        raise ValueError("plan_id must not be blank")
    if day_number < 1:
        raise ValueError("day_number must be at least 1")

    # Do not call a guessed endpoint: the documented Platform API currently
    # exposes Bible passages and VOTD, but not reading-plan schedules/content.
    raise YouVersionUnsupportedError(
        "The YouVersion Platform API does not currently expose reading-plan "
        "day content. Store plan references locally or use an approved content "
        "source before enabling this feature."
    )
