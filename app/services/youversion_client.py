"""Small, synchronous client for scripture data from YouVersion Platform."""

from datetime import datetime, timezone
import threading
import time
from typing import Any

import requests

from app.config import (
    YOUVERSION_API_KEY,
    YOUVERSION_BASE_URL,
    YOUVERSION_TIMEOUT_SECONDS,
)

# Short-lived in-process caches so language switches and menu hops do not
# re-pay YouVersion latency on every USSD keypress.
_CACHE_TTL_SECONDS = 60 * 60
_bibles_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_passage_cache: dict[str, tuple[float, dict[str, str]]] = {}
_votd_id_cache: dict[int, tuple[float, str]] = {}
_cache_lock = threading.Lock()


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


def _cache_get(store: dict[Any, tuple[float, Any]], key: Any) -> Any | None:
    """Return a cached value when present and still fresh."""

    with _cache_lock:
        row = store.get(key)
        if row is None:
            return None
        stamped_at, value = row
        if time.monotonic() - stamped_at > _CACHE_TTL_SECONDS:
            store.pop(key, None)
            return None
        return value


def _cache_set(
    store: dict[Any, tuple[float, Any]], key: Any, value: Any
) -> None:
    """Store a value with a monotonic timestamp."""

    with _cache_lock:
        store[key] = (time.monotonic(), value)


def cached_default_bible_id(language: str) -> int | None:
    """Return a previously fetched default Bible id without hitting the network."""

    cached = _cache_get(_bibles_cache, _normalise_language(language))
    if not cached:
        return None
    bible_id = cached[0].get("id")
    return bible_id if isinstance(bible_id, int) else None


def warm_bibles_for_language(language: str) -> None:
    """Prefetch Bible versions for a language on a daemon thread."""

    language_range = _normalise_language(language)
    if _cache_get(_bibles_cache, language_range) is not None:
        return

    def _run() -> None:
        try:
            list_bibles(language_range, limit=5)
        except YouVersionError:
            return

    threading.Thread(
        target=_run, name=f"warm-bibles-{language_range}", daemon=True
    ).start()


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
    # Always fetch a full page into cache so abbreviation lookups (e.g. NIV)
    # work even after an earlier call requested ``limit=1``.
    page_size = 20
    cache_key = language_range
    cached = _cache_get(_bibles_cache, cache_key)
    if cached is not None:
        return cached[: max(1, min(limit, 20))]

    payload = _request_json(
        "bibles",
        params={
            "language_ranges[]": language_range,
            "page_size": page_size,
        },
    )
    bibles = payload.get("data")
    if not isinstance(bibles, list) or not bibles:
        raise YouVersionNotFoundError(
            f"No licensed Bible version is available for '{language}'. "
            "Accept that language's license in the YouVersion developer portal."
        )

    results: list[dict[str, Any]] = []
    for bible in bibles[:20]:
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
    _cache_set(_bibles_cache, cache_key, results)
    return results[: max(1, min(limit, 20))]


def prefer_bible_id(
    language: str,
    abbreviations: tuple[str, ...] = ("NIV11", "NIV", "NIrV"),
    fallback: int | None = None,
) -> int | None:
    """Pick a licensed Bible by preferred abbreviations (e.g. NIV for kids).

    Args:
        language: Subscriber language code.
        abbreviations: Ordered preference list matched against abbreviation/title.
        fallback: Optional id when none of the abbreviations are licensed.

    Returns:
        Matching Bible id, else ``fallback``, else the first licensed id, else None.
    """

    try:
        bibles = list_bibles(language, limit=20)
    except YouVersionError:
        return fallback

    lowered = [abbr.lower() for abbr in abbreviations]
    for wanted in lowered:
        for bible in bibles:
            haystack = f"{bible['abbreviation']} {bible['title']}".lower()
            if wanted in haystack:
                return int(bible["id"])
    if isinstance(fallback, int) and fallback > 0:
        return fallback
    return int(bibles[0]["id"]) if bibles else None


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
    # HTML passages are reduced to plain text (tags stripped).
    if "<" in content and "yv-v" in content:
        from app.utils.verse_format import parse_verses_from_html

        verses = parse_verses_from_html(content)
        if verses:
            # Plain text without superscripts for AI / SMS reflections.
            return " ".join(text for _num, text in verses)
    if "<" in content:
        from app.utils.verse_format import strip_html

        return strip_html(content)
    return " ".join(content.split())


def get_passage_detail(
    reference: str,
    language: str = "eng",
    bible_id: int | None = None,
) -> dict[str, Any]:
    """Return passage text plus citation metadata from YouVersion.

    Args:
        reference: A USFM passage ID, for example ``"JHN.3.16"`` or ``"PSA.23"``.
        language: ISO 639 or BCP 47 code for the desired Bible language.
        bible_id: Optional preferred Bible version ID from the user session.

    Returns:
        Dict with ``passage_id``, ``reference``, plain ``text``, ``verses``
        (list of ``{n, t}``), and ``text_numbered`` (tiny superscripts).
    """

    from app.services.usfm import format_usfm_reference
    from app.utils.verse_format import (
        numbered_passage_text,
        parse_verses_from_html,
    )

    cleaned_reference = reference.strip()
    if not cleaned_reference:
        raise ValueError("reference must not be blank")

    resolved_bible_id = _get_bible_id(language, bible_id)
    # Version the cache key so older plain-text entries are not reused.
    cache_key = f"{resolved_bible_id}:{cleaned_reference}:v2"
    cached = _cache_get(_passage_cache, cache_key)
    if cached is not None:
        return dict(cached)

    # HTML includes verse markers (yv-v / yv-vlbl) we turn into tiny numbers.
    payload = _request_json(
        f"bibles/{resolved_bible_id}/passages/{cleaned_reference}",
        params={"format": "html"},
    )
    content = payload.get("content")
    if not isinstance(content, str) or not content.strip():
        raise YouVersionNotFoundError(
            "YouVersion returned no text for the requested passage."
        )

    verses_tuples = parse_verses_from_html(content)
    if verses_tuples:
        text = " ".join(piece for _num, piece in verses_tuples)
        text_numbered = numbered_passage_text(verses_tuples)
        verses = [{"n": num, "t": piece} for num, piece in verses_tuples]
    else:
        text = _extract_content({"content": content})
        text_numbered = text
        verses = [{"n": 1, "t": text}] if text else []

    api_reference = payload.get("reference")
    human = (
        str(api_reference).strip()
        if isinstance(api_reference, str) and api_reference.strip()
        else format_usfm_reference(cleaned_reference)
    )
    detail = {
        "passage_id": cleaned_reference,
        "reference": human,
        "text": text,
        "text_numbered": text_numbered,
        "verses": verses,
    }
    _cache_set(_passage_cache, cache_key, detail)
    return dict(detail)


def get_passage(
    reference: str,
    language: str = "eng",
    bible_id: int | None = None,
) -> str:
    """Return a Bible passage as plain text."""

    return get_passage_detail(reference, language, bible_id=bible_id)["text"]


def get_verse_of_the_day_detail(
    language: str = "eng",
    bible_id: int | None = None,
) -> dict[str, str]:
    """Return today's YouVersion Verse of the Day with citation and text."""

    day_of_year = datetime.now(timezone.utc).timetuple().tm_yday
    passage_id = _cache_get(_votd_id_cache, day_of_year)
    if not isinstance(passage_id, str) or not passage_id.strip():
        verse = _request_json(f"verse_of_the_days/{day_of_year}")
        passage_id = verse.get("passage_id")
        if not isinstance(passage_id, str) or not passage_id.strip():
            raise YouVersionNotFoundError(
                "YouVersion did not provide a Verse of the Day reference."
            )
        _cache_set(_votd_id_cache, day_of_year, passage_id)
    return get_passage_detail(passage_id, language, bible_id=bible_id)


def get_verse_of_the_day(
    language: str = "eng",
    bible_id: int | None = None,
) -> str:
    """Return today's curated YouVersion verse as plain text."""

    return get_verse_of_the_day_detail(language, bible_id=bible_id)["text"]


def list_books(
    language: str = "en",
    bible_id: int | None = None,
    testament: str | None = None,
) -> list[dict[str, Any]]:
    """List Bible books for the licensed version, optionally by testament.

    Args:
        language: Language used to resolve ``bible_id`` when unset.
        bible_id: Optional saved Bible version id.
        testament: ``old`` / ``new`` / ``None`` for all.

    Returns:
        Books with ``id``, ``title``, ``canon``, and ``chapter_count``.
    """

    resolved_bible_id = _get_bible_id(language, bible_id)
    payload = _request_json(f"bibles/{resolved_bible_id}/books")
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise YouVersionError("YouVersion returned no Bible books.")

    wanted = None
    if testament in {"old", "ot", "old_testament"}:
        wanted = "old_testament"
    elif testament in {"new", "nt", "new_testament"}:
        wanted = "new_testament"

    results: list[dict[str, Any]] = []
    for book in rows:
        if not isinstance(book, dict):
            continue
        book_id = book.get("id")
        if not isinstance(book_id, str) or not book_id:
            continue
        canon = str(book.get("canon") or "")
        if wanted and canon != wanted:
            continue
        chapters = book.get("chapters")
        chapter_count = len(chapters) if isinstance(chapters, list) else 0
        results.append(
            {
                "id": book_id,
                "title": str(book.get("title") or book_id),
                "canon": canon,
                "chapter_count": chapter_count,
            }
        )
    if not results:
        raise YouVersionNotFoundError("No books available for that testament.")
    return results


def get_book_chapter_count(
    book_usfm: str,
    language: str = "en",
    bible_id: int | None = None,
) -> int:
    """Return how many chapters a book has in the licensed Bible."""

    books = list_books(language, bible_id=bible_id, testament=None)
    for book in books:
        if book["id"].upper() == book_usfm.upper():
            return int(book["chapter_count"])
    raise YouVersionNotFoundError(f"Book '{book_usfm}' not found.")


def get_chapter_verse_count(
    book_usfm: str,
    chapter: int,
    language: str = "en",
    bible_id: int | None = None,
) -> int:
    """Return verse count for one chapter via the chapters collection."""

    resolved_bible_id = _get_bible_id(language, bible_id)
    payload = _request_json(
        f"bibles/{resolved_bible_id}/books/{book_usfm.upper()}/chapters"
    )
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise YouVersionError("YouVersion returned no chapters.")
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("id")) == str(chapter) or str(row.get("title")) == str(
            chapter
        ):
            verses = row.get("verses")
            if isinstance(verses, list) and verses:
                return len(verses)
    raise YouVersionNotFoundError(
        f"Chapter {chapter} not found in {book_usfm}."
    )


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
