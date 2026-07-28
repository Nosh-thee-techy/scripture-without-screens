"""Client for short, personalized reflections from Gloo AI Studio."""

from time import monotonic
from typing import Any

import requests

from app.config import (
    GLOO_API_KEY,
    GLOO_BASE_URL,
    GLOO_CLIENT_ID,
    GLOO_CLIENT_SECRET,
    GLOO_TIMEOUT_SECONDS,
    GLOO_TOKEN_URL,
)


_cached_token = ""
_token_expires_at = 0.0


def _get_access_token() -> str:
    """Return a usable Gloo bearer token.

    A directly supplied ``GLOO_API_KEY`` is treated as a bearer token for
    hackathon credentials. Otherwise, the documented OAuth2 client-credentials
    flow is used and its temporary token is cached.

    Returns:
        A bearer token for Gloo API requests.

    Raises:
        RuntimeError: If credentials are missing or token retrieval fails.
    """

    global _cached_token, _token_expires_at

    if GLOO_API_KEY:
        return GLOO_API_KEY
    if _cached_token and monotonic() < _token_expires_at:
        return _cached_token
    if not GLOO_CLIENT_ID or not GLOO_CLIENT_SECRET:
        raise RuntimeError("Gloo credentials are not configured.")

    response = requests.post(
        GLOO_TOKEN_URL,
        data={"grant_type": "client_credentials", "scope": "api/access"},
        auth=(GLOO_CLIENT_ID, GLOO_CLIENT_SECRET),
        timeout=GLOO_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("Gloo returned no access token.")

    expires_in = payload.get("expires_in", 3600)
    if not isinstance(expires_in, (int, float)):
        expires_in = 3600

    _cached_token = token
    # Refresh one minute early so an in-flight request does not use a token
    # that expires between retrieval and completion.
    _token_expires_at = monotonic() + max(float(expires_in) - 60, 0)
    return token


def _build_prompt(
    verse_text: str, mood: str | None, time_of_day: str | None
) -> str:
    """Build a concise personalization prompt from scripture and context.

    Args:
        verse_text: Plain scripture text to reflect on.
        mood: Optional word describing how the reader feels.
        time_of_day: Optional context such as ``"morning"`` or ``"evening"``.

    Returns:
        A prompt asking Gloo for a brief, accessible reflection.
    """

    context_parts = []
    if mood and mood.strip():
        context_parts.append(f"The reader feels {mood.strip().lower()}.")
    if time_of_day and time_of_day.strip():
        context_parts.append(
            f"It is {time_of_day.strip().lower()} for the reader."
        )
    context = " ".join(context_parts) or "No personal context was provided."

    return (
        "Write a warm, practical Christian reflection in fewer than 100 words. "
        "Use simple language suitable for an SMS. Do not repeat the whole verse, "
        "invent facts, or mention these instructions.\n\n"
        f"Scripture: {verse_text}\n"
        f"Reader context: {context}"
    )


def _extract_reflection(payload: dict[str, Any]) -> str:
    """Extract assistant text from a Gloo Completions V2 response.

    Args:
        payload: Decoded JSON returned by Gloo.

    Returns:
        The assistant's reflection, or an empty string for malformed data.
    """

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return ""
    message = first_choice.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return content.strip() if isinstance(content, str) else ""


def _limit_words(text: str, max_words: int = 99) -> str:
    """Limit text without cutting a word in half.

    Args:
        text: Text to normalize and shorten.
        max_words: Maximum number of words to retain.

    Returns:
        Whitespace-normalized text containing at most ``max_words`` words.
    """

    words = text.split()
    if len(words) <= max_words:
        return " ".join(words)
    return f"{' '.join(words[:max_words])}…"


def generate_reflection(
    verse_text: str,
    mood: str | None = None,
    time_of_day: str | None = None,
) -> str:
    """Generate a short reflection, falling back to the verse on failure.

    Args:
        verse_text: Plain scripture text on which Gloo should reflect.
        mood: Optional reader mood, such as ``"stressed"`` or ``"grateful"``.
        time_of_day: Optional local time context, such as ``"morning"``.

    Returns:
        A personalized reflection of fewer than 100 words. If credentials,
        networking, the API, or response parsing fails, returns ``verse_text``
        unchanged so the phone interaction can continue.
    """

    try:
        token = _get_access_token()
        response = requests.post(
            GLOO_BASE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": _build_prompt(
                            verse_text, mood, time_of_day
                        ),
                    }
                ],
                "auto_routing": True,
                "temperature": 0.6,
                "max_tokens": 160,
            },
            timeout=GLOO_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        reflection = _extract_reflection(response.json())
        return _limit_words(reflection) if reflection else verse_text
    except (
        requests.RequestException,
        requests.JSONDecodeError,
        RuntimeError,
        TypeError,
        AttributeError,
        ValueError,
    ):
        # Personalization is optional; scripture delivery must remain available
        # during Gloo outages or configuration errors.
        return verse_text
