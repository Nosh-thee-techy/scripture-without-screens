"""Tests for Redis-backed session preferences."""

from app.utils.session_store import (
    clear_user_session,
    get_user_session,
    reset_session_backend_for_tests,
    update_user_session,
)


def test_update_user_session_persists_language_and_plan_day() -> None:
    """Ensure preference updates are readable on the next load."""

    reset_session_backend_for_tests()
    phone = "+254711111111"
    clear_user_session(phone)

    update_user_session(
        phone,
        language="sw",
        plan_day=3,
        bible_id=111,
        language_set=True,
        age_band="6_9",
    )
    session = get_user_session(phone)

    assert session["language"] == "sw"
    assert session["plan_day"] == 3
    assert session["bible_id"] == 111
    assert session["language_set"] is True
    assert session["age_band"] == "6_9"
    assert session["kids_story_id"] is None
