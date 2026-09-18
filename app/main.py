"""FastAPI application entrypoint for feature-phone webhooks."""

from __future__ import annotations

import logging
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import DAILY_SMS_HOUR_UTC
from app.routes.analytics import router as analytics_router
from app.routes.jobs import router as jobs_router
from app.routes.sms import router as sms_router
from app.routes.ussd import router as ussd_router
from app.routes.voice import router as voice_router
from app.routes.whatsapp import router as whatsapp_router
from app.services.daily_sms import send_daily_sms_blast


logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Scripture Without Screens",
    description="Bible access through USSD, SMS, and voice channels.",
    version="0.1.0",
)

app.include_router(ussd_router)
app.include_router(sms_router)
app.include_router(voice_router)
app.include_router(jobs_router)
app.include_router(whatsapp_router)
app.include_router(analytics_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_scheduler: BackgroundScheduler | None = None


def _run_scheduled_daily_sms() -> None:
    """Fire the daily SMS blast and log sent/failed counts."""

    logger.info(
        "Scheduled daily SMS job starting (hour_utc=%s).",
        DAILY_SMS_HOUR_UTC,
    )
    try:
        summary = send_daily_sms_blast(dry_run=False)
    except Exception as exc:  # noqa: BLE001 - never crash the scheduler thread
        logger.warning("Scheduled daily SMS job failed: %s", exc)
        return
    logger.info(
        "Scheduled daily SMS job finished: %s",
        summary,
    )


def _start_daily_sms_scheduler() -> BackgroundScheduler:
    """Create and start the once-per-day SMS BackgroundScheduler.

    Returns:
        The running scheduler instance.
    """

    hour = max(0, min(23, int(DAILY_SMS_HOUR_UTC)))
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        _run_scheduled_daily_sms,
        trigger="cron",
        hour=hour,
        minute=0,
        id="daily_sms_blast",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Daily SMS scheduler started (cron %02d:00 UTC).",
        hour,
    )
    return scheduler


@app.on_event("startup")
def on_startup() -> None:
    """Start background jobs when the API process boots."""

    global _scheduler
    if _scheduler is None:
        _scheduler = _start_daily_sms_scheduler()


@app.on_event("shutdown")
def on_shutdown() -> None:
    """Stop the background scheduler cleanly on process exit."""

    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Daily SMS scheduler shut down.")


@app.get("/")
def feature_phone_demo() -> FileResponse:
    """Serve the judge-facing feature-phone USSD simulator.

    Returns:
        The HTML page that dials the live ``/ussd`` webhook.
    """

    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health_check() -> dict[str, str]:
    """Return a lightweight process health response.

    Returns:
        A dictionary confirming that the API process is running.
    """

    return {"status": "ok"}
