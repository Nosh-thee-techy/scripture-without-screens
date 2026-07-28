"""Tests for feature-phone text length helpers."""

import pytest

from app.utils.formatters import format_for_sms, format_for_ussd, truncate_text


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
