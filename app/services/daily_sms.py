"""Build and send daily morning SMS (VOTD + reading-plan verse)."""

from __future__ import annotations

import logging
from typing import Any

from app.services.africastalking_client import AfricasTalkingError, send_sms
from app.services.reading_plan import get_plan_reference, plan_label
from app.services.youversion_client import (
    YouVersionError,
    get_verse_of_the_day_detail,
)
from app.utils.formatters import format_for_sms
from app.utils.session_store import list_daily_sms_subscribers


logger = logging.getLogger(__name__)


def build_daily_sms_body(session: dict[str, Any]) -> str:
    """Compose one SMS for VOTD plus the subscriber's plan reference.

    Args:
        session: Persisted user preferences.

    Returns:
        A single SMS-sized message string.
    """

    language = str(session.get("language") or "en")
    bible_id = session.get("bible_id")
    parts: list[str] = []
    try:
        votd = get_verse_of_the_day_detail(
            language=language, bible_id=bible_id
        )
        parts.append(f"VOTD {votd['reference']}: {votd['text']}")
    except YouVersionError:
        parts.append("VOTD unavailable today. Dial USSD for Scripture.")

    plan_id = str(session.get("plan_id") or "hope-kenya")
    day = int(session.get("plan_day") or 1)
    try:
        reference = get_plan_reference(plan_id, day)
        label = plan_label(plan_id)
        parts.append(f"Read {label} D{day}: {reference}")
    except ValueError:
        pass

    return format_for_sms(" | ".join(parts))


def send_daily_sms_blast(*, dry_run: bool = False) -> dict[str, Any]:
    """Send (or preview) daily SMS to every opted-in subscriber.

    Args:
        dry_run: When True, build messages but do not call Africa's Talking.

    Returns:
        Summary counts and optional sample bodies for dry runs.
    """

    subscribers = list_daily_sms_subscribers()
    sent = 0
    failed = 0
    samples: list[dict[str, str]] = []

    for phone, session in subscribers:
        try:
            body = build_daily_sms_body(session)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Daily SMS build failed for %s: %s", phone, exc)
            failed += 1
            continue

        if dry_run:
            samples.append({"phone": phone, "body": body})
            sent += 1
            continue

        try:
            send_sms(body, phone)
            sent += 1
        except (AfricasTalkingError, ValueError) as exc:
            logger.warning("Daily SMS send failed for %s: %s", phone, exc)
            failed += 1

    result: dict[str, Any] = {
        "subscribers": len(subscribers),
        "sent": sent,
        "failed": failed,
        "dry_run": dry_run,
    }
    if dry_run:
        result["samples"] = samples[:20]
    return result
