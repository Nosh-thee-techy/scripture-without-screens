"""Tests for tiny verse numbers and YouVersion HTML parsing."""

from app.utils.formatters import paginate_verse_units
from app.utils.verse_format import (
    format_verse_unit,
    numbered_passage_text,
    parse_verses_from_html,
    tiny_verse_number,
)


def test_tiny_verse_number_uses_superscripts() -> None:
    assert tiny_verse_number(31) == "³¹"
    assert tiny_verse_number(1) == "¹"


def test_parse_verses_from_youversion_html() -> None:
    html = (
        '<div><div class="p">'
        '<span class="yv-v" v="1"></span><span class="yv-vlbl">1</span>'
        "In the beginning God created the heavens and the earth. "
        '<span class="yv-v" v="2"></span><span class="yv-vlbl">2</span>'
        "And the earth was waste and void."
        "</div></div>"
    )
    verses = parse_verses_from_html(html)
    assert verses == [
        (1, "In the beginning God created the heavens and the earth."),
        (2, "And the earth was waste and void."),
    ]
    numbered = numbered_passage_text(verses)
    assert numbered.startswith("¹In the beginning")
    assert "²And the earth" in numbered


def test_paginate_verse_units_hides_actions_until_last_page() -> None:
    verses = [(n, f"Verse number {n} has some words here.") for n in range(1, 20)]
    pages = paginate_verse_units(
        "Genesis 1",
        verses,
        footer="1. Next chapter\n2. Pray with me\n0. Home",
        more_line="9. More",
        continue_footer="0. Home",
    )
    assert len(pages) > 1
    first_screen, first_verse = pages[0]
    last_screen, _last_verse = pages[-1]
    assert first_verse == 1
    assert "9. More" in first_screen
    assert "Pray with me" not in first_screen
    assert format_verse_unit(1, "x").startswith("¹")
    assert "¹" in first_screen or "1" in tiny_verse_number(1)
    assert "Pray with me" in last_screen
    assert "9. More" not in last_screen
