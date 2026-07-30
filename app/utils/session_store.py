"""Redis-backed preferences for feature-phone users.

Each subscriber is keyed by phone number so language, Bible version, and
reading-plan progress survive across USSD dials, SMS messages, and voice calls.
If Redis is unavailable, an in-process dictionary is used so local demos still
work; restart the app and those preferences are lost.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import REDIS_URL, SESSION_TTL_SECONDS

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "en"
DEFAULT_PLAN_DAY = 1
SESSION_KEY_PREFIX = "sws:user:"

_memory_sessions: dict[str, dict[str, Any]] = {}
_redis_client: Any | None = None
_redis_checked = False


def _get_redis() -> Any | None:
    """Return a connected Redis client, or ``None`` when Redis is unavailable.

    Returns:
        A ``redis.Redis`` instance when the server accepts a ping; otherwise
        ``None`` so callers can fall back to memory.
    """

    global _redis_client, _redis_checked

    if _redis_checked:
        return _redis_client

    _redis_checked = True
    try:
        import redis

        client = redis.Redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        client.ping()
        _redis_client = client
        logger.info("Redis session store connected at %s", REDIS_URL)
    except Exception as exc:
        # Prefer continuing the call over failing the farmer's USSD session.
        _redis_client = None
        logger.warning(
            "Redis unavailable (%s); using in-memory sessions.", exc
        )
    return _redis_client


def _session_key(phone_number: str) -> str:
    """Build the Redis key for one subscriber.

    Args:
        phone_number: International phone number from Africa's Talking.

    Returns:
        A namespaced Redis key string.
    """

    return f"{SESSION_KEY_PREFIX}{phone_number.strip()}"


def _default_session() -> dict[str, Any]:
    """Return a fresh preference document for a new subscriber.

    Returns:
        Default language, unset Bible ID, and plan day one.
    """

    return {
        "language": DEFAULT_LANGUAGE,
        "bible_id": None,
        "plan_day": DEFAULT_PLAN_DAY,
        "plan_id": "hope-kenya",
    }


def get_user_session(phone_number: str) -> dict[str, Any]:
    """Load persisted preferences for a phone number.

    Args:
        phone_number: Subscriber MSISDN, for example ``"+2547..."``.

    Returns:
        A mutable copy of the user's session document. Missing users receive
        defaults without writing until ``save_user_session`` is called.
    """

    key = _session_key(phone_number)
    client = _get_redis()

    if client is not None:
        raw = client.get(key)
        if raw:
            try:
                payload = json.loads(raw)
                if isinstance(payload, dict):
                    merged = _default_session()
                    merged.update(payload)
                    return merged
            except json.JSONDecodeError:
                logger.warning("Corrupt Redis session for %s; resetting.", key)

    if key in _memory_sessions:
        return dict(_memory_sessions[key])
    return _default_session()


def save_user_session(phone_number: str, session: dict[str, Any]) -> None:
    """Persist a subscriber's preferences.

    Args:
        phone_number: Subscriber MSISDN.
        session: Preference document to store.
    """

    key = _session_key(phone_number)
    payload = json.dumps(session)
    client = _get_redis()

    if client is not None:
        client.set(key, payload, ex=SESSION_TTL_SECONDS)
    _memory_sessions[key] = dict(session)


def update_user_session(phone_number: str, **fields: Any) -> dict[str, Any]:
    """Merge fields into a user's session and save the result.

    Args:
        phone_number: Subscriber MSISDN.
        **fields: Preference keys to overwrite, such as ``language`` or
            ``bible_id``.

    Returns:
        The updated session document.
    """

    session = get_user_session(phone_number)
    session.update(fields)
    save_user_session(phone_number, session)
    return session


def clear_user_session(phone_number: str) -> None:
    """Remove stored preferences for a phone number.

    Args:
        phone_number: Subscriber MSISDN.
    """

    key = _session_key(phone_number)
    client = _get_redis()
    if client is not None:
        client.delete(key)
    _memory_sessions.pop(key, None)


def reset_session_backend_for_tests() -> None:
    """Clear memory sessions and force Redis reconnect on the next call.

    Returns:
        None. Intended for unit tests only.
    """

    global _redis_client, _redis_checked

    _memory_sessions.clear()
    _redis_client = None
    _redis_checked = False
