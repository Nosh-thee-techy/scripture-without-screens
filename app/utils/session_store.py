"""Redis-backed preferences for feature-phone users.

Each subscriber is keyed by phone number so language, Bible version, and
reading-plan progress survive across USSD dials, SMS messages, and voice calls.
If Redis is unavailable, an in-process dictionary is used so local demos still
work; restart the app and those preferences are lost.
"""

from __future__ import annotations

import json
import logging
import threading
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
    # Hard cap: Windows TCP stacks sometimes ignore short redis timeouts.
    # Language pick must not wait on a missing Redis server.
    probe_result: dict[str, Any] = {"client": None, "error": None}

    def _probe() -> None:
        try:
            import redis

            kwargs: dict[str, Any] = {
                "decode_responses": True,
                "socket_connect_timeout": 0.15,
                "socket_timeout": 0.25,
                "retry_on_timeout": False,
            }
            try:
                from redis.backoff import NoBackoff
                from redis.retry import Retry

                kwargs["retry"] = Retry(NoBackoff(), 0)
            except Exception:
                pass

            client = redis.Redis.from_url(REDIS_URL, **kwargs)
            client.ping()
            probe_result["client"] = client
        except Exception as exc:  # noqa: BLE001 - prefer memory over USSD hang
            probe_result["error"] = exc

    worker = threading.Thread(target=_probe, name="redis-probe", daemon=True)
    worker.start()
    worker.join(0.35)
    if worker.is_alive() or probe_result["client"] is None:
        _redis_client = None
        reason = probe_result["error"] or "connect timed out"
        logger.warning(
            "Redis unavailable (%s); using in-memory sessions.", reason
        )
        return _redis_client

    _redis_client = probe_result["client"]
    logger.info("Redis session store connected at %s", REDIS_URL)
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
        Default language, unset Bible ID, plan day one, and kids-flow fields.
    """

    return {
        "language": DEFAULT_LANGUAGE,
        "language_set": False,
        "bible_id": None,
        "plan_day": DEFAULT_PLAN_DAY,
        "plan_id": "hope-kenya",
        "age_band": None,
        "kids_story_id": None,
        "kids_section": 0,
        "kids_quiz_index": 0,
        "kids_quiz_retries": 0,
        "ussd_flow": "boot",
        "voice_flow": "boot",
        # Daily morning SMS (VOTD + plan verse) when True.
        "sms_daily": True,
        # Verse of the Day + Read My Bible navigation
        "votd_passage_id": None,
        "read_testament": None,
        "read_book": None,
        "read_chapter": None,
        "read_verse": 1,
        "read_book_page": 0,
        "read_chapter_page": 0,
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


def list_daily_sms_subscribers() -> list[tuple[str, dict[str, Any]]]:
    """Return ``(phone, session)`` pairs opted into daily SMS.

    Scans Redis when available, otherwise the in-memory demo store.
    """

    results: list[tuple[str, dict[str, Any]]] = []
    client = _get_redis()
    if client is not None:
        try:
            for key in client.scan_iter(match=f"{SESSION_KEY_PREFIX}*", count=100):
                raw = client.get(key)
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                if not payload.get("language_set"):
                    continue
                if payload.get("sms_daily", True) is False:
                    continue
                phone = str(key).removeprefix(SESSION_KEY_PREFIX)
                merged = _default_session()
                merged.update(payload)
                results.append((phone, merged))
            return results
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis scan for SMS subscribers failed: %s", exc)

    for key, payload in _memory_sessions.items():
        if not payload.get("language_set"):
            continue
        if payload.get("sms_daily", True) is False:
            continue
        phone = key.removeprefix(SESSION_KEY_PREFIX)
        results.append((phone, dict(payload)))
    return results


def reset_session_backend_for_tests() -> None:
    """Clear memory sessions and force Redis reconnect on the next call.

    Returns:
        None. Intended for unit tests only.
    """

    global _redis_client, _redis_checked

    _memory_sessions.clear()
    _redis_client = None
    _redis_checked = False
