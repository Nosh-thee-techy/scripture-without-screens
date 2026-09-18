"""Tests for Redis-backed session preferences and phone hashing."""

import hashlib

from app.utils.session_store import (
    SESSION_KEY_PREFIX,
    _hash_phone,
    _session_key,
    clear_user_session,
    get_user_session,
    list_all_sessions,
    list_daily_sms_subscribers,
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


def test_hash_phone_is_sha256_hex_of_stripped_msisdn() -> None:
    """Ensure Redis keys never embed the raw dialable number."""

    phone = " +254700000001 "
    digest = _hash_phone(phone)
    expected = hashlib.sha256(b"+254700000001").hexdigest()
    assert digest == expected
    assert _session_key(phone) == f"{SESSION_KEY_PREFIX}{expected}"
    assert "+254" not in _session_key(phone)


def test_save_embeds_phone_and_last_active_for_sms_and_analytics() -> None:
    """Session JSON must carry phone_number; updates stamp last_active_at."""

    reset_session_backend_for_tests()
    phone = "+254722222222"
    clear_user_session(phone)

    updated = update_user_session(phone, language="en", language_set=True)
    assert updated["phone_number"] == phone
    assert isinstance(updated["last_active_at"], str)
    assert "T" in updated["last_active_at"]

    loaded = get_user_session(phone)
    assert loaded["phone_number"] == phone
    assert loaded["last_active_at"] == updated["last_active_at"]

    subscribers = list_daily_sms_subscribers()
    assert any(entry[0] == phone for entry in subscribers)

    all_sessions = list_all_sessions()
    assert any(row.get("phone_number") == phone for row in all_sessions)
