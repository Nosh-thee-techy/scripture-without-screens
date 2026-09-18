"""Tests for GET /analytics/summary."""

from fastapi.testclient import TestClient

from app.main import app
from app.utils.session_store import (
    clear_user_session,
    reset_session_backend_for_tests,
    update_user_session,
)


client = TestClient(app)


def test_analytics_summary_counts_hashed_sessions(monkeypatch: object) -> None:
    """Ensure summary returns aggregates without requiring Redis."""

    reset_session_backend_for_tests()
    monkeypatch.setattr("app.routes.analytics.ANALYTICS_SECRET", "")
    monkeypatch.setattr("app.config.ANALYTICS_SECRET", "")

    phone_a = "+254700000010"
    phone_b = "+254700000011"
    clear_user_session(phone_a)
    clear_user_session(phone_b)
    update_user_session(
        phone_a,
        language="sw",
        language_set=True,
        ussd_flow="main",
        sms_daily=True,
    )
    update_user_session(
        phone_b,
        language="en",
        language_set=True,
        wa_flow="main",
        sms_daily=False,
    )

    response = client.get("/analytics/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_users"] >= 2
    assert payload["language_breakdown"].get("sw", 0) >= 1
    assert payload["language_breakdown"].get("en", 0) >= 1
    assert payload["channel_breakdown"]["ussd"] >= 1
    assert payload["channel_breakdown"]["whatsapp"] >= 1
    assert payload["active_last_7_days"] >= 2
    assert "phone_number" not in payload
    assert payload["daily_sms_subscribers"] >= 1


def test_analytics_summary_requires_secret_when_configured(
    monkeypatch: object,
) -> None:
    """Mirror /jobs/daily-sms auth when ANALYTICS_SECRET is set."""

    monkeypatch.setattr("app.routes.analytics.ANALYTICS_SECRET", "test-secret")
    denied = client.get("/analytics/summary")
    assert denied.status_code == 401

    allowed = client.get(
        "/analytics/summary",
        headers={"X-Analytics-Secret": "test-secret"},
    )
    assert allowed.status_code == 200
