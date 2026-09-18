"""Application configuration loaded from environment variables.

This module is the single source of truth for external API credentials, base
URLs, and request timeouts. Secrets must be supplied through the environment
or a local ``.env`` file and must never be committed to source control.
"""

import os

from dotenv import load_dotenv


load_dotenv()


def _env(name: str, default: str = "") -> str:
    """Read an environment variable and strip whitespace/quotes.

    Args:
        name: Environment variable name.
        default: Fallback when the variable is unset.

    Returns:
        A cleaned string value safe for API clients.
    """

    return os.getenv(name, default).strip().strip('"').strip("'")


YOUVERSION_API_KEY = _env("YOUVERSION_API_KEY")
YOUVERSION_BASE_URL = _env(
    "YOUVERSION_BASE_URL", "https://api.youversion.com/v1"
).rstrip("/")
YOUVERSION_TIMEOUT_SECONDS = float(
    _env("YOUVERSION_TIMEOUT_SECONDS", "10") or "10"
)

GLOO_API_KEY = _env("GLOO_API_KEY")
GLOO_CLIENT_ID = _env("GLOO_CLIENT_ID")
GLOO_CLIENT_SECRET = _env("GLOO_CLIENT_SECRET")
GLOO_BASE_URL = _env(
    "GLOO_BASE_URL",
    "https://platform.ai.gloo.com/ai/v2/chat/completions",
)
GLOO_TOKEN_URL = _env(
    "GLOO_TOKEN_URL", "https://platform.ai.gloo.com/oauth2/token"
)
GLOO_TIMEOUT_SECONDS = float(_env("GLOO_TIMEOUT_SECONDS", "15") or "15")

AT_API_KEY = _env("AT_API_KEY")
AT_USERNAME = _env("AT_USERNAME", "sandbox") or "sandbox"


FEATHERLESS_API_KEY = _env("FEATHERLESS_API_KEY")
FEATHERLESS_BASE_URL = _env(
    "FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1"
).rstrip("/")
FEATHERLESS_MODEL = _env(
    "FEATHERLESS_MODEL", "Qwen/Qwen2.5-7B-Instruct"
) or "Qwen/Qwen2.5-7B-Instruct"
FEATHERLESS_GEMMA_MODEL = _env(
    "FEATHERLESS_GEMMA_MODEL", "google/gemma-2-9b-it"
) or "google/gemma-2-9b-it"
FEATHERLESS_TIMEOUT_SECONDS = float(
    _env("FEATHERLESS_TIMEOUT_SECONDS", "30") or "30"
)

OLLAMA_BASE_URL = _env(
    "OLLAMA_BASE_URL", "http://localhost:11434"
).rstrip("/")
OLLAMA_MODEL = _env("OLLAMA_MODEL", "gemma2:2b") or "gemma2:2b"
OLLAMA_TIMEOUT_SECONDS = float(
    _env("OLLAMA_TIMEOUT_SECONDS", "20") or "20"
)

ELEVENLABS_API_KEY = _env("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = _env("ELEVENLABS_VOICE_ID")
ELEVENLABS_BASE_URL = _env(
    "ELEVENLABS_BASE_URL", "https://api.elevenlabs.io/v1"
).rstrip("/")
ELEVENLABS_MODEL_ID = _env(
    "ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"
) or "eleven_multilingual_v2"
ELEVENLABS_TIMEOUT_SECONDS = float(
    _env("ELEVENLABS_TIMEOUT_SECONDS", "45") or "45"
)

# Public HTTPS base (ngrok) so Africa's Talking can Play generated audio.
PUBLIC_BASE_URL = _env("PUBLIC_BASE_URL").rstrip("/")

# Redis remembers language, Bible version, and reading-plan day per phone.
REDIS_URL = _env("REDIS_URL", "redis://localhost:6379/0")
SESSION_TTL_SECONDS = int(
    _env("SESSION_TTL_SECONDS", str(60 * 60 * 24 * 30)) or str(60 * 60 * 24 * 30)
)

# Optional secret for POST /jobs/daily-sms (cron / scheduler).
DAILY_SMS_JOB_SECRET = _env("DAILY_SMS_JOB_SECRET")

# Hour (0-23 UTC) when the in-process daily SMS scheduler fires.
# Default 05 ≈ early morning East Africa Time (UTC+3).
DAILY_SMS_HOUR_UTC = int(_env("DAILY_SMS_HOUR_UTC", "05") or "05")

# Optional secret for GET /analytics/summary (X-Analytics-Secret header).
ANALYTICS_SECRET = _env("ANALYTICS_SECRET")

# Meta WhatsApp Cloud API (test number or production phone number).
WHATSAPP_ACCESS_TOKEN = _env("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = _env("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_BUSINESS_ACCOUNT_ID = _env("WHATSAPP_BUSINESS_ACCOUNT_ID")
WHATSAPP_VERIFY_TOKEN = _env("WHATSAPP_VERIFY_TOKEN", "sws-whatsapp-verify")
WHATSAPP_API_VERSION = _env("WHATSAPP_API_VERSION", "v22.0") or "v22.0"
WHATSAPP_APP_SECRET = _env("WHATSAPP_APP_SECRET")
WHATSAPP_TIMEOUT_SECONDS = float(
    _env("WHATSAPP_TIMEOUT_SECONDS", "15") or "15"
)
