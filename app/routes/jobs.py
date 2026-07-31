"""Internal job endpoints (cron-friendly) for daily SMS and similar tasks."""

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from app.config import DAILY_SMS_JOB_SECRET
from app.services.daily_sms import build_daily_sms_body, send_daily_sms_blast
from app.utils.session_store import get_user_session


router = APIRouter(tags=["jobs"])


def _authorize(secret: str | None) -> None:
    """Reject unauthorized job calls when a secret is configured."""

    if not DAILY_SMS_JOB_SECRET:
        return
    if secret != DAILY_SMS_JOB_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized job call.")


@router.post("/jobs/daily-sms")
def run_daily_sms_job(
    dry_run: Annotated[bool, Query()] = False,
    x_job_secret: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    """Send morning VOTD + plan-verse SMS to opted-in subscribers.

    Schedule with cron, for example::

        curl -X POST -H "X-Job-Secret: $DAILY_SMS_JOB_SECRET" \\
          https://your-host/jobs/daily-sms
    """

    _authorize(x_job_secret)
    summary = send_daily_sms_blast(dry_run=dry_run)
    return JSONResponse(summary)


@router.get("/demo/daily-sms")
def preview_daily_sms(
    phone: Annotated[str, Query()] = "+254711000111",
) -> JSONResponse:
    """Preview the daily SMS body for one phone without sending."""

    session = get_user_session(phone)
    body = build_daily_sms_body(session)
    return JSONResponse({"phone": phone, "body": body})
