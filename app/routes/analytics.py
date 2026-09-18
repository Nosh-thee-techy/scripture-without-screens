"""Internal analytics endpoints for aggregate Scripture Without Screens usage.

Protected the same way as ``/jobs/daily-sms``: when ``ANALYTICS_SECRET`` is
set, callers must send matching ``X-Analytics-Secret``. Counts use hashed
Redis session keys so partners see aggregates without raw MSISDNs in key
space.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

from app.config import ANALYTICS_SECRET
from app.utils.session_store import list_all_sessions, list_daily_sms_subscribers


router = APIRouter(tags=["analytics"])


def _authorize(secret: str | None) -> None:
    """Reject unauthorized analytics calls when a secret is configured."""

    if not ANALYTICS_SECRET:
        return
    if secret != ANALYTICS_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized analytics call.")


def _parse_iso(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp from a session field, if present."""

    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _channel_flags(session: dict[str, Any]) -> dict[str, bool]:
    """Infer which channels a session has actually used.

    Args:
        session: One stored preference document.

    Returns:
        Booleans for ``ussd``, ``sms``, ``voice``, and ``whatsapp``.
    """

    ussd_flow = str(session.get("ussd_flow") or "boot")
    voice_flow = str(session.get("voice_flow") or "boot")
    wa_flow = session.get("wa_flow")
    return {
        "ussd": ussd_flow not in {"boot", ""},
        "sms": bool(session.get("sms_daily", True))
        and bool(session.get("language_set")),
        "voice": voice_flow not in {"boot", ""},
        "whatsapp": bool(wa_flow) and str(wa_flow) not in {"boot", ""},
    }


def build_analytics_summary() -> dict[str, Any]:
    """Aggregate session documents into a privacy-safe usage summary.

    Returns:
        Counts and breakdowns with no raw phone numbers in the payload.
    """

    sessions = list_all_sessions()
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    language_breakdown: dict[str, int] = {}
    channel_breakdown = {"ussd": 0, "sms": 0, "voice": 0, "whatsapp": 0}
    active_last_7_days = 0

    for session in sessions:
        language = str(session.get("language") or "en")
        language_breakdown[language] = language_breakdown.get(language, 0) + 1

        stamped = _parse_iso(session.get("last_active_at"))
        if stamped is not None:
            if stamped.tzinfo is None:
                stamped = stamped.replace(tzinfo=timezone.utc)
            if stamped >= cutoff:
                active_last_7_days += 1

        for channel, used in _channel_flags(session).items():
            if used:
                channel_breakdown[channel] += 1

    return {
        "total_users": len(sessions),
        "active_last_7_days": active_last_7_days,
        "language_breakdown": language_breakdown,
        "channel_breakdown": channel_breakdown,
        "daily_sms_subscribers": len(list_daily_sms_subscribers()),
    }


@router.get("/analytics/summary")
def analytics_summary(
    x_analytics_secret: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    """Return aggregate, privacy-safe usage stats for YouVersion/partners.

    Never includes raw phone numbers or message content — only hashed-session
    counts and language/channel breakdowns.

    Example::

        curl -H "X-Analytics-Secret: $ANALYTICS_SECRET" \\
          https://your-host/analytics/summary
    """

    _authorize(x_analytics_secret)
    return JSONResponse(build_analytics_summary())
