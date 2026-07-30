"""ElevenLabs text-to-speech client for voice-call scripture audio."""

from __future__ import annotations

import uuid
from pathlib import Path

import requests

from app.config import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_BASE_URL,
    ELEVENLABS_MODEL_ID,
    ELEVENLABS_TIMEOUT_SECONDS,
    ELEVENLABS_VOICE_ID,
)


AUDIO_DIR = Path(__file__).resolve().parent.parent / "static" / "audio"


class ElevenLabsError(RuntimeError):
    """Raised when ElevenLabs cannot synthesize speech."""


def synthesize_speech(text: str, language_code: str | None = None) -> Path:
    """Convert text to an MP3 file under ``app/static/audio``.

    Args:
        text: Plain text to narrate.
        language_code: Optional ISO language hint for multilingual models.

    Returns:
        Filesystem path to the generated MP3.

    Raises:
        ValueError: If ``text`` is blank.
        ElevenLabsError: If credentials are missing or synthesis fails.
    """

    cleaned = " ".join(text.split())
    if not cleaned:
        raise ValueError("text must not be blank")
    if not ELEVENLABS_API_KEY or not ELEVENLABS_VOICE_ID:
        raise ElevenLabsError(
            "ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID must be configured."
        )

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.mp3"
    destination = AUDIO_DIR / filename

    payload: dict[str, object] = {
        "text": cleaned,
        "model_id": ELEVENLABS_MODEL_ID,
    }
    # language_code is ignored by some models; safe to omit when unset.
    if language_code and language_code.strip():
        payload["language_code"] = language_code.strip().lower()[:2]

    try:
        response = requests.post(
            f"{ELEVENLABS_BASE_URL}/text-to-speech/{ELEVENLABS_VOICE_ID}",
            headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=ELEVENLABS_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ElevenLabsError("ElevenLabs could not synthesize speech.") from exc

    if not response.content:
        raise ElevenLabsError("ElevenLabs returned empty audio.")

    destination.write_bytes(response.content)
    return destination


def audio_public_path(audio_file: Path) -> str:
    """Return the URL path served by FastAPI for a generated audio file.

    Args:
        audio_file: Path created by ``synthesize_speech``.

    Returns:
        A path such as ``/static/audio/<id>.mp3``.
    """

    return f"/static/audio/{audio_file.name}"
