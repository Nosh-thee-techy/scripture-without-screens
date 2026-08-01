"""Tests for feature-phone text length helpers."""

import pytest

from app.utils.formatters import (
    format_for_sms,
    format_for_ussd,
    paginate_ussd,
    truncate_text,
    ussd_page,
)


def test_sms_text_fits_one_message() -> None:
    """Ensure long SMS text is shortened to the configured limit."""

    result = format_for_sms("encouraging words " * 30)

    assert len(result) <= 160
    assert result.endswith("...")


def test_ussd_text_leaves_room_for_end_prefix() -> None:
    """Ensure formatted USSD content fits after Africa's Talking's prefix."""

    result = format_for_ussd("scripture words " * 30)

    assert len(f"END {result}") <= 160


def test_truncate_text_rejects_impossible_limit() -> None:
    """Ensure a limit shorter than its suffix is rejected clearly."""

    with pytest.raises(ValueError):
        truncate_text("hello", max_length=2)


def test_paginate_ussd_keeps_full_chapter_readable() -> None:
    """Long chapter text should become multiple pages with a More key."""

    body = "God is our refuge and strength. " * 40
    footer = "1. Next chapter\n2. Pray with me\n0. Home"
    more = "9. More"
    pages = paginate_ussd(body, footer, more)

    assert len(pages) > 1
    assert "9. More" in pages[0]
    assert "9. More" not in pages[-1]
    assert all(len(f"CON {page}") <= 182 for page in pages)
    # Every word from the body should appear across the pages.
    joined = " ".join(pages)
    assert "refuge" in joined
    assert "strength" in joined


def test_ussd_page_advances_with_has_more_flag() -> None:
    """Page helper should report when more text remains."""

    body = " ".join(f"verse{n}" for n in range(80))
    footer = "0. Home"
    screen0, total, more0 = ussd_page(body, footer, "9. More", page=0)
    screen1, total2, more1 = ussd_page(body, footer, "9. More", page=1)

    assert total == total2
    assert total >= 2
    assert more0 is True
    assert "9. More" in screen0
    assert screen0 != screen1
    assert "verse0" in screen0
    if total == 2:
        assert more1 is False
        assert "9. More" not in screen1
