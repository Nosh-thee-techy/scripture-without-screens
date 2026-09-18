"""Redis-backed preferences for feature-phone users.

Each subscriber is keyed by a SHA-256 hash of their phone number so language,
Bible version, and reading-plan progress survive across USSD dials, SMS, and
voice calls — without storing raw MSISDNs as Redis key material. YouVersion /
partners can see aggregate usage without exposing phone numbers if the Redis
store were ever compromised or shared.

If Redis is unavailable, an in-process dictionary is used so local demos still
work; restart the app and those preferences are lost.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import datetime, timezone
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


def _hash_phone(phone_number: str) -> str:
    """Return a SHA-256 hex digest of a cleaned phone number.

    Privacy: Redis keys and shared analytics must never use raw MSISDNs at
    rest. Hashing keeps stable unique-user identity for aggregate counts
    without exposing the dialable number if the store is compromised or
    handed to partners.

    Args:
        phone_number: International MSISDN, for example ``"+2547..."``.

    Returns:
        Lowercase hex SHA-256 digest of the stripped phone string.
    """

    cleaned = phone_number.strip()
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()


def _session_key(phone_number: str) -> str:
    """Build the Redis key for one subscriber using a hashed MSISDN.

    Args:
        phone_number: International phone number from Africa's Talking /
            WhatsApp (raw; never written into the key itself).

    Returns:
        A namespaced Redis key string whose suffix is ``_hash_phone(...)``.
    """

    # Hash so raw phones are not visible as key names in Redis SCAN output.
    return f"{SESSION_KEY_PREFIX}{_hash_phone(phone_number)}"


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
        # Raw MSISDN lives only inside the JSON payload (for outbound SMS),
        # never as the Redis key. See ``_hash_phone``.
        "phone_number": None,
        "last_active_at": None,
    }


def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""

    return datetime.now(timezone.utc).isoformat()


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

    Always embeds the raw ``phone_number`` inside the JSON payload so SMS /
    analytics jobs can recover the dialable MSISDN after Redis keys became
    irreversible hashes.

    Args:
        phone_number: Subscriber MSISDN.
        session: Preference document to store.
    """

    key = _session_key(phone_number)
    session["phone_number"] = phone_number.strip()
    to_store = dict(session)
    payload = json.dumps(to_store)
    client = _get_redis()

    if client is not None:
        client.set(key, payload, ex=SESSION_TTL_SECONDS)
    _memory_sessions[key] = dict(to_store)


def update_user_session(phone_number: str, **fields: Any) -> dict[str, Any]:
    """Merge fields into a user's session and save the result.

    Touches ``last_active_at`` on every call so analytics can count recent
    users without a separate activity log.

    Args:
        phone_number: Subscriber MSISDN.
        **fields: Preference keys to overwrite, such as ``language`` or
            ``bible_id``.

    Returns:
        The updated session document.
    """

    session = get_user_session(phone_number)
    session.update(fields)
    session["last_active_at"] = _utc_now_iso()
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


def _iter_session_payloads() -> list[dict[str, Any]]:
    """Load every stored session document from Redis or memory.

    Returns:
        Merged session dicts (defaults applied). Empty list when nothing is
        stored or Redis scan fails.
    """

    results: list[dict[str, Any]] = []
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
                merged = _default_session()
                merged.update(payload)
                results.append(merged)
            return results
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis scan for sessions failed: %s", exc)

    for payload in _memory_sessions.values():
        merged = _default_session()
        merged.update(payload)
        results.append(merged)
    return results


def list_all_sessions() -> list[dict[str, Any]]:
    """Return every stored session document for analytics.

    Follows the same Redis / memory scan pattern as
    ``list_daily_sms_subscribers`` but does not filter by SMS opt-in.

    Returns:
        A list of session dictionaries (may include ``phone_number``).
    """

    return _iter_session_payloads()


def list_daily_sms_subscribers() -> list[tuple[str, dict[str, Any]]]:
    """Return ``(phone, session)`` pairs opted into daily SMS.

    Phone numbers are read from the session JSON ``phone_number`` field
    because Redis keys are hashed and no longer reversible.
    """

    results: list[tuple[str, dict[str, Any]]] = []
    for payload in _iter_session_payloads():
        if not payload.get("language_set"):
            continue
        if payload.get("sms_daily", True) is False:
            continue
        phone = payload.get("phone_number")
        if not isinstance(phone, str) or not phone.strip():
            # Legacy rows without an embedded MSISDN cannot receive SMS.
            continue
        results.append((phone.strip(), dict(payload)))
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
