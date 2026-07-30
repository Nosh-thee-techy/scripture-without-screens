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


# Labels shown on USSD menus; codes are BCP 47 ranges for /v1/bibles.
SUPPORTED_LANGUAGES: list[tuple[str, str]] = [
    ("en", "English"),
    ("sw", "Swahili"),
    ("kln", "Kalenjin"),
    ("ki", "Kikuyu"),
    ("luo", "Dholuo"),
]


def _normalise_language(language: str) -> str:
    """Convert a supported language code to the BCP 47 form used by YouVersion.

    Args:
        language: An ISO 639 language code, such as ``"eng"`` or ``"en"``.

    Returns:
        A BCP 47-compatible language range.
    """

    aliases = {
        "eng": "en",
        "swa": "sw",
        "swh": "sw",
        "kal": "kln",
        "kik": "ki",
        "luo": "luo",
    }
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


def list_bibles(language: str, limit: int = 5) -> list[dict[str, Any]]:
    """List licensed Bible versions available for a language.

    Args:
        language: ISO 639 or BCP 47 language code.
        limit: Maximum number of versions to return for USSD menus.

    Returns:
        A list of dictionaries with ``id``, ``abbreviation``, and ``title``.

    Raises:
        YouVersionNotFoundError: If no licensed Bible is available.
        YouVersionError: If the API request or response is invalid.
    """

    language_range = _normalise_language(language)
    payload = _request_json(
        "bibles",
        params={
            "language_ranges[]": language_range,
            "page_size": max(1, min(limit, 20)),
        },
    )
    bibles = payload.get("data")
    if not isinstance(bibles, list) or not bibles:
        raise YouVersionNotFoundError(
            f"No licensed Bible version is available for '{language}'. "
            "Accept that language's license in the YouVersion developer portal."
        )

    results: list[dict[str, Any]] = []
    for bible in bibles[:limit]:
        if not isinstance(bible, dict):
            continue
        bible_id = bible.get("id")
        if not isinstance(bible_id, int):
            continue
        abbreviation = bible.get("abbreviation") or bible.get(
            "localized_abbreviation"
        ) or str(bible_id)
        title = bible.get("title") or bible.get("localized_title") or abbreviation
        results.append(
            {
                "id": bible_id,
                "abbreviation": str(abbreviation),
                "title": str(title),
            }
        )

    if not results:
        raise YouVersionError("YouVersion returned no usable Bible versions.")
    return results


def _get_bible_id(language: str, bible_id: int | None = None) -> int:
    """Resolve a Bible ID from an explicit choice or the first licensed version.

    Args:
        language: ISO 639 or BCP 47 language code.
        bible_id: Optional saved version ID from Redis.

    Returns:
        The numeric Bible version ID to use for passage requests.

    Raises:
        YouVersionNotFoundError: If no licensed Bible is available.
        YouVersionError: If YouVersion returns malformed version data.
    """

    if isinstance(bible_id, int) and bible_id > 0:
        return bible_id
    return list_bibles(language, limit=1)[0]["id"]


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


def get_verse_of_the_day(
    language: str = "eng",
    bible_id: int | None = None,
) -> str:
    """Return today's curated YouVersion verse as plain text.

    Args:
        language: ISO 639 or BCP 47 code for the desired Bible language.
        bible_id: Optional preferred Bible version ID from the user session.

    Returns:
        Today's verse text in the requested or first licensed version.

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
    return get_passage(passage_id, language, bible_id=bible_id)


def get_passage(
    reference: str,
    language: str = "eng",
    bible_id: int | None = None,
) -> str:
    """Return a Bible passage as plain text.

    Args:
        reference: A USFM passage ID, for example ``"JHN.3.16"``.
        language: ISO 639 or BCP 47 code for the desired Bible language.
        bible_id: Optional preferred Bible version ID from the user session.

    Returns:
        Plain passage text in the requested or first licensed version.

    Raises:
        ValueError: If ``reference`` is blank.
        YouVersionNotFoundError: If no matching passage or translation exists.
        YouVersionError: If the API request or response is invalid.
    """

    cleaned_reference = reference.strip()
    if not cleaned_reference:
        raise ValueError("reference must not be blank")

    resolved_bible_id = _get_bible_id(language, bible_id)
    payload = _request_json(
        f"bibles/{resolved_bible_id}/passages/{cleaned_reference}",
        params={"format": "text"},
    )
    return _extract_content(payload)


def get_reading_plan_day(plan_id: str, day_number: int) -> str:
    """Return the local plan reference for a day (not YouVersion plan APIs).

    Args:
        plan_id: Local plan identifier such as ``"hope-kenya"``.
        day_number: One-based day number within that plan.

    Returns:
        The USFM reference string for that day.

    Raises:
        ValueError: If ``plan_id`` is blank, ``day_number`` is invalid, or the
            local plan does not define that day.
    """

    from app.services.reading_plan import get_plan_reference

    if not plan_id.strip():
        raise ValueError("plan_id must not be blank")
    if day_number < 1:
        raise ValueError("day_number must be at least 1")
    return get_plan_reference(plan_id, day_number)
