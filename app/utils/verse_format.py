"""Tiny verse numbers and HTML verse parsing for feature-phone reading."""

from __future__ import annotations

import html
import re
from typing import Any


_SUPER_TRANS = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
_VERSE_SPLIT = re.compile(
    r'<span class="yv-v"\s+v="(\d+)"\s*></span>\s*'
    r'(?:<span class="yv-vlbl">[^<]*</span>)?',
    re.IGNORECASE,
)
_TAG = re.compile(r"<[^>]+>")


def tiny_verse_number(verse: int) -> str:
    """Render a verse number as compact Unicode superscript digits."""

    return str(int(verse)).translate(_SUPER_TRANS)


def format_verse_unit(verse: int, text: str) -> str:
    """Prefix verse text with a tiny superscript number (no trailing space)."""

    cleaned = " ".join(text.split()).strip()
    return f"{tiny_verse_number(verse)}{cleaned}"


def strip_html(fragment: str) -> str:
    """Remove tags and decode entities from one HTML fragment."""

    plain = _TAG.sub(" ", fragment)
    plain = html.unescape(plain)
    return " ".join(plain.split()).strip()


def parse_verses_from_html(content: str) -> list[tuple[int, str]]:
    """Extract ``(verse_number, plain_text)`` pairs from YouVersion HTML."""

    if not content or not content.strip():
        return []

    parts = _VERSE_SPLIT.split(content)
    # split yields: [preamble, num, body, num, body, ...]
    verses: list[tuple[int, str]] = []
    index = 1
    while index + 1 < len(parts):
        try:
            number = int(parts[index])
        except ValueError:
            index += 2
            continue
        body = strip_html(parts[index + 1])
        if body:
            verses.append((number, body))
        index += 2
    return verses


def numbered_passage_text(
    verses: list[tuple[int, str]] | list[dict[str, Any]],
) -> str:
    """Join verse units into one USSD/SMS-friendly body."""

    units: list[str] = []
    for item in verses:
        if isinstance(item, dict):
            number = int(item["n"])
            text = str(item.get("t") or "")
        else:
            number, text = item
        if text.strip():
            units.append(format_verse_unit(number, text))
    return " ".join(units)


def first_verse_number(verses: list[tuple[int, str]] | list[dict[str, Any]]) -> int:
    """Return the first verse number, defaulting to 1."""

    if not verses:
        return 1
    first = verses[0]
    if isinstance(first, dict):
        return int(first.get("n") or 1)
    return int(first[0])
