"""Client for short, personalized reflections (Featherless, then Gloo)."""

from time import monotonic
from typing import Any

import requests

from app.config import (
    FEATHERLESS_API_KEY,
    FEATHERLESS_BASE_URL,
    FEATHERLESS_MODEL,
    FEATHERLESS_TIMEOUT_SECONDS,
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
        A prompt asking for a brief, accessible reflection.
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
    """Extract assistant text from an OpenAI-style chat completion response.

    Args:
        payload: Decoded JSON returned by Featherless or Gloo.

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


def _reflect_with_featherless(prompt: str) -> str:
    """Request a reflection from Featherless chat completions.

    Args:
        prompt: Fully formed user prompt.

    Returns:
        Reflection text, or an empty string when the call fails.
    """

    if not FEATHERLESS_API_KEY:
        return ""

    response = requests.post(
        f"{FEATHERLESS_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {FEATHERLESS_API_KEY}",
            "Content-Type": "application/json",
            "X-Title": "Scripture Without Screens",
        },
        json={
            "model": FEATHERLESS_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.6,
            "max_tokens": 160,
        },
        timeout=FEATHERLESS_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return _extract_reflection(response.json())


def _reflect_with_gloo(prompt: str) -> str:
    """Request a reflection from Gloo Completions V2.

    Args:
        prompt: Fully formed user prompt.

    Returns:
        Reflection text, or an empty string when the call fails.
    """

    token = _get_access_token()
    response = requests.post(
        GLOO_BASE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "messages": [{"role": "user", "content": prompt}],
            "auto_routing": True,
            "temperature": 0.6,
            "max_tokens": 160,
        },
        timeout=GLOO_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return _extract_reflection(response.json())


def generate_reflection(
    verse_text: str,
    mood: str | None = None,
    time_of_day: str | None = None,
) -> str:
    """Generate a short reflection, falling back to the verse on failure.

    Prefers Featherless when configured (no card required), then Gloo, then
    returns the original verse so SMS/USSD never breaks.

    Args:
        verse_text: Plain scripture text on which the model should reflect.
        mood: Optional reader mood, such as ``"stressed"`` or ``"grateful"``.
        time_of_day: Optional local time context, such as ``"morning"``.

    Returns:
        A personalized reflection of fewer than 100 words, or ``verse_text``.
    """

    prompt = _build_prompt(verse_text, mood, time_of_day)

    try:
        reflection = _reflect_with_featherless(prompt)
        if reflection:
            return _limit_words(reflection)
    except (
        requests.RequestException,
        requests.JSONDecodeError,
        RuntimeError,
        TypeError,
        AttributeError,
        ValueError,
        KeyError,
    ):
        pass

    try:
        reflection = _reflect_with_gloo(prompt)
        if reflection:
            return _limit_words(reflection)
    except (
        requests.RequestException,
        requests.JSONDecodeError,
        RuntimeError,
        TypeError,
        AttributeError,
        ValueError,
        KeyError,
    ):
        pass

    return verse_text
