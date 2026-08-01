"""Text formatting helpers for feature-phone channels."""


SMS_CHARACTER_LIMIT = 160
USSD_RESPONSE_LIMIT = 160
USSD_CONTROL_PREFIX_LENGTH = len("END ")
# Safaricom and many AT networks accept ~182 chars for a CON/END payload
# including the ``CON `` / ``END `` prefix.
USSD_CON_LIMIT = 182
USSD_CON_PREFIX_LENGTH = len("CON ")


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """Normalize and shorten text without cutting a word when possible.

    Args:
        text: Plain text to prepare for phone delivery.
        max_length: Maximum number of characters in the returned text.
        suffix: Marker appended when truncation is required.

    Returns:
        Whitespace-normalized text no longer than ``max_length`` characters.

    Raises:
        ValueError: If the limit cannot contain the truncation suffix.
    """

    if max_length < len(suffix):
        raise ValueError("max_length must be at least as long as suffix")

    normalized = " ".join(text.split())
    if len(normalized) <= max_length:
        return normalized

    available_length = max_length - len(suffix)
    shortened = normalized[:available_length].rsplit(" ", 1)[0]
    if not shortened:
        shortened = normalized[:available_length]
    return f"{shortened}{suffix}"


def _normalize_body(text: str) -> str:
    """Collapse whitespace while keeping intentional paragraph breaks light."""

    return " ".join(text.replace("\r\n", "\n").replace("\n", " ").split())


def _chunk_words(text: str, chunk_size: int) -> list[str]:
    """Split normalized text into word-aware chunks of at most ``chunk_size``."""

    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")
    if not text:
        return [""]
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= chunk_size:
            chunks.append(remaining)
            break
        window = remaining[:chunk_size]
        cut = window.rsplit(" ", 1)[0]
        if not cut:
            cut = window
        chunks.append(cut)
        remaining = remaining[len(cut) :].lstrip()
    return chunks


def paginate_ussd(
    body: str,
    footer: str,
    more_line: str,
    *,
    limit: int | None = None,
) -> list[str]:
    """Build CON-screen pages so long scripture can be read via ``More``.

    Args:
        body: Verse/chapter/explanation text (may be long).
        footer: Menu lines always shown (e.g. next / pray / home).
        more_line: Line shown when another page remains (e.g. ``9. More``).
        limit: Max characters for the message body after ``CON ``.

    Returns:
        One or more complete USSD menu strings, each within ``limit``.
    """

    content_limit = (
        limit
        if limit is not None
        else USSD_CON_LIMIT - USSD_CON_PREFIX_LENGTH
    )
    normalized = _normalize_body(body)
    footer = footer.strip("\n")
    more_line = more_line.strip()

    # Reserve space for More + footer on every chunk estimate; the last page
    # drops More and can therefore show a bit more text.
    reserved = len(more_line) + len(footer) + 2
    chunk_size = max(24, content_limit - reserved)
    chunks = _chunk_words(normalized, chunk_size)
    pages: list[str] = []
    for index, chunk in enumerate(chunks):
        if index < len(chunks) - 1:
            page = f"{chunk}\n{more_line}\n{footer}"
        else:
            page = f"{chunk}\n{footer}"
        # Hard safety: if a page still overruns (very long footer words), trim body.
        if len(page) > content_limit:
            overflow = len(page) - content_limit
            trimmed = truncate_text(chunk, max(24, len(chunk) - overflow), suffix="")
            page = (
                f"{trimmed}\n{more_line}\n{footer}"
                if index < len(chunks) - 1
                else f"{trimmed}\n{footer}"
            )
        pages.append(page)
    return pages or [footer]


def ussd_page(
    body: str,
    footer: str,
    more_line: str,
    page: int = 0,
    *,
    limit: int | None = None,
) -> tuple[str, int, bool]:
    """Return one paginated CON screen plus paging metadata.

    Returns:
        ``(screen_text, total_pages, has_more)``.
    """

    pages = paginate_ussd(body, footer, more_line, limit=limit)
    total = len(pages)
    index = max(0, min(int(page), total - 1))
    has_more = index < total - 1
    return pages[index], total, has_more


def format_for_sms(text: str) -> str:
    """Format text as a single SMS-sized message.

    Args:
        text: Plain text to send by SMS.

    Returns:
        Normalized text of at most 160 characters.
    """

    # Three ASCII periods preserve GSM-7 compatibility better than a Unicode
    # ellipsis when the rest of the message also uses GSM-7 characters.
    return truncate_text(text, SMS_CHARACTER_LIMIT)


def format_for_ussd(text: str) -> str:
    """Format content so its complete ``END`` response fits 160 characters.

    Args:
        text: Plain text to display before the USSD session closes.

    Returns:
        Normalized text sized to leave room for Africa's Talking's ``END ``
        control prefix.
    """

    content_limit = USSD_RESPONSE_LIMIT - USSD_CONTROL_PREFIX_LENGTH
    return truncate_text(text, content_limit)
