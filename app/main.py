"""FastAPI application entrypoint for feature-phone webhooks."""

from fastapi import FastAPI

from app.routes.sms import router as sms_router
from app.routes.ussd import router as ussd_router
from app.routes.voice import router as voice_router


app = FastAPI(
    title="Scripture Without Screens",
    description="Bible access through USSD, SMS, and voice channels.",
    version="0.1.0",
)

app.include_router(ussd_router)
app.include_router(sms_router)
app.include_router(voice_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Return a lightweight process health response.

    Returns:
        A dictionary confirming that the API process is running.
    """

    return {"status": "ok"}
