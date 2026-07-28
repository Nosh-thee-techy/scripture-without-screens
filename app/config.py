"""Application configuration loaded from environment variables.

This module is the single source of truth for external API credentials, base
URLs, and request timeouts. Secrets must be supplied through the environment
or a local ``.env`` file and must never be committed to source control.
"""

import os

from dotenv import load_dotenv


load_dotenv()

YOUVERSION_API_KEY = os.getenv("YOUVERSION_API_KEY", "")
YOUVERSION_BASE_URL = os.getenv(
    "YOUVERSION_BASE_URL", "https://api.youversion.com/v1"
).rstrip("/")
YOUVERSION_TIMEOUT_SECONDS = float(
    os.getenv("YOUVERSION_TIMEOUT_SECONDS", "10")
)

GLOO_API_KEY = os.getenv("GLOO_API_KEY", "")
GLOO_CLIENT_ID = os.getenv("GLOO_CLIENT_ID", "")
GLOO_CLIENT_SECRET = os.getenv("GLOO_CLIENT_SECRET", "")
GLOO_BASE_URL = os.getenv(
    "GLOO_BASE_URL",
    "https://platform.ai.gloo.com/ai/v2/chat/completions",
)
GLOO_TOKEN_URL = os.getenv(
    "GLOO_TOKEN_URL", "https://platform.ai.gloo.com/oauth2/token"
)
GLOO_TIMEOUT_SECONDS = float(os.getenv("GLOO_TIMEOUT_SECONDS", "15"))

AT_API_KEY = os.getenv("AT_API_KEY", "")
AT_USERNAME = os.getenv("AT_USERNAME", "sandbox")
