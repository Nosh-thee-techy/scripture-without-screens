"""Kids Corner AI helpers: simplify and translate with a resilient cascade.

Order: Featherless primary (Qwen) → Featherless Gemma → local Ollama Gemma →
plain template fallback. Timeouts advance to the next backend so USSD stays
responsive.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from app.config import (
    FEATHERLESS_API_KEY,
    FEATHERLESS_BASE_URL,
    FEATHERLESS_GEMMA_MODEL,
    FEATHERLESS_MODEL,
    FEATHERLESS_TIMEOUT_SECONDS,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT_SECONDS,
)
from app.services.youversion_client import SUPPORTED_LANGUAGES


logger = logging.getLogger(__name__)

_LANGUAGE_NAMES = {code: label for code, label in SUPPORTED_LANGUAGES}


def _language_name(language: str) -> str:
    """Map a language code to a human label for prompts.

    Args:
        language: BCP 47 / ISO code such as ``sw``.

    Returns:
        A display name, defaulting to English.
    """

    return _LANGUAGE_NAMES.get(language, "English")


def _age_phrase(age_band: str) -> str:
    """Describe an age band for the model.

    Args:
        age_band: ``u6``, ``6_9``, or ``10_12``.

    Returns:
        A short age phrase.
    """

    mapping = {
        "u6": "a child under 6",
        "6_9": "a child aged 6 to 9",
        "10_12": "a child aged 10 to 12",
    }
    return mapping.get(age_band, "a child")


def _extract_chat_text(payload: dict[str, Any]) -> str:
    """Pull assistant text from an OpenAI-style chat payload.

    Args:
        payload: Decoded JSON response.

    Returns:
        Assistant content, or empty string.
    """

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
    text = first.get("text")
    return text.strip() if isinstance(text, str) else ""


def _limit_chars(text: str, max_chars: int = 120) -> str:
    """Hard-cap text for USSD screens without mid-word cuts when possible.

    Args:
        text: Model or fallback text.
        max_chars: Maximum characters.

    Returns:
        Truncated, whitespace-normalized text.
    """

    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    shortened = normalized[: max_chars - 3].rsplit(" ", 1)[0]
    if not shortened:
        shortened = normalized[: max_chars - 3]
    return f"{shortened}..."


def _featherless_chat(model: str, prompt: str) -> str:
    """Call Featherless chat completions for one model.

    Args:
        model: Featherless model id.
        prompt: User prompt.

    Returns:
        Model text, or empty string on failure.
    """

    if not FEATHERLESS_API_KEY:
        return ""
    try:
        response = requests.post(
            f"{FEATHERLESS_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {FEATHERLESS_API_KEY}",
                "Content-Type": "application/json",
                "X-Title": "Scripture Without Screens Kids",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.5,
                "max_tokens": 120,
            },
            timeout=FEATHERLESS_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return _extract_chat_text(response.json())
    except Exception as exc:
        logger.info("Featherless kids AI failed (%s): %s", model, exc)
        return ""


def _ollama_chat(prompt: str) -> str:
    """Call local Ollama chat API.

    Args:
        prompt: User prompt.

    Returns:
        Model text, or empty string when Ollama is down.
    """

    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.5, "num_predict": 120},
            },
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        message = payload.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content.strip()
        return ""
    except Exception as exc:
        logger.info("Ollama kids AI failed: %s", exc)
        return ""


def _cascade(prompt: str) -> str:
    """Run the Qwen → Gemma → Ollama cascade.

    Args:
        prompt: Fully formed instruction.

    Returns:
        First non-empty model response, or empty string.
    """

    for model in (FEATHERLESS_MODEL, FEATHERLESS_GEMMA_MODEL):
        text = _featherless_chat(model, prompt)
        if text:
            return text
    return _ollama_chat(prompt)


def _plain_simplify_fallback(text: str, language: str) -> str:
    """Build a no-LLM simpler line when all models fail.

    Args:
        text: Original section text.
        language: Target language code (used only for a short prefix hint).

    Returns:
        A short plain explanation with a concrete example cue.
    """

    _ = language
    core = _limit_chars(text, 70)
    return _limit_chars(
        f"Simple: {core} Example: be kind and brave like in the story.",
        120,
    )


def simplify_for_kid(
    text: str,
    language: str = "en",
    age_band: str = "6_9",
    max_chars: int = 120,
) -> str:
    """Rewrite a story section so a child can understand it.

    Args:
        text: Original section (usually English).
        language: Subscriber language code for the reply.
        age_band: Age band controlling vocabulary.
        max_chars: Hard character cap for USSD.

    Returns:
        A short simpler explanation, ideally in ``language``.
    """

    lang_name = _language_name(language)
    age = _age_phrase(age_band)
    prompt = (
        f"Explain this Bible story bit to {age}. "
        f"Reply ONLY in {lang_name}. Use very simple words and one tiny "
        f"everyday example. Max 40 words. No emojis.\n\nStory bit:\n{text}"
    )
    result = _cascade(prompt)
    if result:
        return _limit_chars(result, max_chars)
    return _plain_simplify_fallback(text, language)


def explain_scripture(
    reference: str,
    text: str,
    language: str = "en",
    max_chars: int = 140,
) -> str:
    """Explain a Bible verse simply for USSD, in the subscriber's language."""

    lang_name = _language_name(language)
    prompt = (
        f"Explain this Bible verse briefly for an adult reader. "
        f"Reply ONLY in {lang_name}. Max 45 words. Warm, clear, practical. "
        f"Do not invent history. No emojis.\n\n"
        f"Reference: {reference}\nVerse: {text}"
    )
    result = _cascade(prompt)
    if result:
        return _limit_chars(result, max_chars)
    return _limit_chars(
        f"{reference}: God speaks through this verse—read it slowly and live it today.",
        max_chars,
    )


def write_prayer(
    reference: str,
    text: str,
    language: str = "en",
    max_chars: int = 140,
) -> str:
    """Write a short prayer inspired by a verse, for USSD."""

    lang_name = _language_name(language)
    prompt = (
        f"Write a short Christian prayer for today based on this verse. "
        f"Reply ONLY in {lang_name}. Max 40 words. Start with 'God,' or "
        f"'Lord,'. No emojis.\n\nReference: {reference}\nVerse: {text}"
    )
    result = _cascade(prompt)
    if result:
        return _limit_chars(result, max_chars)
    return _limit_chars(
        f"Lord, thank You for {reference}. Help me understand and live Your word today. Amen.",
        max_chars,
    )


def explain_votd_for_kid(
    reference: str,
    text: str,
    language: str = "en",
    age_band: str = "6_9",
    max_chars: int = 140,
) -> str:
    """Explain Verse of the Day for a child — meaning + example only.

    Never rewrite the verse; the caller shows the real Bible text separately.
    """

    lang_name = _language_name(language)
    age = _age_phrase(age_band)
    prompt = (
        f"A child ({age}) will already see the real Bible verse separately. "
        f"Do NOT rewrite, paraphrase, or quote the verse as if it were new wording. "
        f"Reply ONLY in {lang_name}. Use exactly this shape:\n"
        f"What it means:\n"
        f"<2 short sentences, accurate to the verse>\n\n"
        f"For example:\n"
        f"<1 short real-life example a child would recognise>\n"
        f"Warm and clear. No emojis. No headings besides those two.\n\n"
        f"Reference: {reference}\nVerse (for your accuracy only): {text}"
    )
    result = _cascade(prompt)
    if result:
        cleaned = "\n".join(
            line.rstrip() for line in result.replace("\r\n", "\n").split("\n")
        ).strip()
        while "\n\n\n" in cleaned:
            cleaned = cleaned.replace("\n\n\n", "\n\n")
        if len(cleaned) <= max_chars:
            return cleaned
        return _limit_chars(cleaned, max_chars)
    return _limit_chars(
        "What it means:\n"
        "God is speaking a true word to help you live well today.\n\n"
        "For example:\n"
        "When you choose kindness, you are living what this verse teaches.",
        max_chars,
    )


def kids_prayer(
    topic: str,
    language: str = "en",
    age_band: str = "6_9",
    max_chars: int = 140,
) -> str:
    """Short child-friendly prayer about a story or verse topic."""

    lang_name = _language_name(language)
    age = _age_phrase(age_band)
    prompt = (
        f"Write a short prayer for {age} about: {topic}. "
        f"Reply ONLY in {lang_name}. Max 35 words. Start with 'God,' or "
        f"'Dear God,'. End with Amen. No emojis."
    )
    result = _cascade(prompt)
    if result:
        return _limit_chars(result, max_chars)
    return _limit_chars(
        f"Dear God, thank You for teaching me about {topic}. Help me love You and others today. Amen.",
        max_chars,
    )


def kids_affirmation(
    topic: str,
    language: str = "en",
    age_band: str = "6_9",
    max_chars: int = 120,
) -> str:
    """Short word of affirmation based on what the child learned."""

    lang_name = _language_name(language)
    age = _age_phrase(age_band)
    prompt = (
        f"Write one short word of affirmation for {age} based on: {topic}. "
        f"Reply ONLY in {lang_name}. Max 30 words. Start with 'You' or "
        f"'Remember'. Warm and true. No emojis."
    )
    result = _cascade(prompt)
    if result:
        return _limit_chars(result, max_chars)
    return _limit_chars(
        f"You are loved by God. What you learned about {topic} can help you today.",
        max_chars,
    )


def translate_line(
    text: str,
    language: str = "en",
    age_band: str = "6_9",
    max_chars: int = 120,
) -> str:
    """Translate a short kids line into the subscriber's language.

    Args:
        text: English source line.
        language: Target language code.
        age_band: Age band for tone.
        max_chars: Hard character cap.

    Returns:
        Translated (or original English) text.
    """

    if language in {"", "en"}:
        return _limit_chars(text, max_chars)

    lang_name = _language_name(language)
    age = _age_phrase(age_band)
    prompt = (
        f"Translate for {age} into {lang_name} only. Keep it joyful and "
        f"simple. Max 40 words. No notes.\n\nText:\n{text}"
    )
    result = _cascade(prompt)
    if result:
        return _limit_chars(result, max_chars)
    return _limit_chars(text, max_chars)
