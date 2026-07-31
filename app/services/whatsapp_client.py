"""Meta WhatsApp Cloud API client (send + webhook helpers)."""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

import requests

from app.config import (
    WHATSAPP_ACCESS_TOKEN,
    WHATSAPP_API_VERSION,
    WHATSAPP_APP_SECRET,
    WHATSAPP_PHONE_NUMBER_ID,
    WHATSAPP_TIMEOUT_SECONDS,
)


logger = logging.getLogger(__name__)


class WhatsAppError(RuntimeError):
    """Raised when WhatsApp Cloud API cannot complete a request."""


def whatsapp_configured() -> bool:
    """Return True when token and phone-number id are present."""

    return bool(WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID)


def _messages_url() -> str:
    """Build the Cloud API messages endpoint for the configured number."""

    if not WHATSAPP_PHONE_NUMBER_ID:
        raise WhatsAppError(
            "WHATSAPP_PHONE_NUMBER_ID is not configured. "
            "Add it from Meta → WhatsApp → API setup."
        )
    version = WHATSAPP_API_VERSION.lstrip("/")
    return (
        f"https://graph.facebook.com/{version}/"
        f"{WHATSAPP_PHONE_NUMBER_ID}/messages"
    )


def _post_message(payload: dict[str, Any]) -> dict[str, Any]:
    """POST one Cloud API message payload and return decoded JSON."""

    if not WHATSAPP_ACCESS_TOKEN:
        raise WhatsAppError(
            "WHATSAPP_ACCESS_TOKEN is not configured. "
            "Paste a temporary or system user token from Meta."
        )
    try:
        response = requests.post(
            _messages_url(),
            headers={
                "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=WHATSAPP_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise WhatsAppError("Could not reach WhatsApp Cloud API.") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise WhatsAppError("WhatsApp returned invalid JSON.") from exc

    if response.status_code >= 400:
        error = data.get("error") if isinstance(data, dict) else None
        detail = ""
        if isinstance(error, dict):
            detail = str(error.get("message") or error)
        raise WhatsAppError(
            f"WhatsApp API HTTP {response.status_code}: {detail or data}"
        )
    if not isinstance(data, dict):
        raise WhatsAppError("WhatsApp returned an unexpected response.")
    return data


def send_whatsapp_text(to_phone: str, body: str) -> dict[str, Any]:
    """Send a plain-text WhatsApp message via Cloud API.

    Args:
        to_phone: Recipient MSISDN in international form (``2547...`` or
            ``+2547...``). The ``+`` is stripped for the API.
        body: Message text (WhatsApp allows longer than SMS).

    Returns:
        Decoded JSON from Meta.

    Raises:
        ValueError: If inputs are blank.
        WhatsAppError: If credentials or the HTTP call fail.
    """

    if not body.strip():
        raise ValueError("body must not be blank")
    if not to_phone.strip():
        raise ValueError("to_phone must not be blank")

    recipient = to_phone.strip().lstrip("+")
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "text",
        "text": {"preview_url": False, "body": body.strip()},
    }
    return _post_message(payload)


def send_whatsapp_image(
    to_phone: str,
    image_url: str,
    caption: str = "",
) -> dict[str, Any]:
    """Send an image message (public HTTPS link) with optional caption.

    Args:
        to_phone: Recipient MSISDN.
        image_url: Publicly reachable HTTPS URL (e.g. ngrok ``/static/kids/...``).
        caption: Optional caption (WhatsApp caps around 1024 chars).

    Returns:
        Decoded JSON from Meta.
    """

    if not to_phone.strip():
        raise ValueError("to_phone must not be blank")
    if not image_url.strip():
        raise ValueError("image_url must not be blank")

    recipient = to_phone.strip().lstrip("+")
    image: dict[str, Any] = {"link": image_url.strip()}
    if caption.strip():
        image["caption"] = caption.strip()[:1024]
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "image",
        "image": image,
    }
    return _post_message(payload)


def send_whatsapp_messages(
    to_phone: str, messages: list[dict[str, Any]]
) -> None:
    """Send a sequence of text/image WhatsApp parts.

    Each item is ``{"type": "text", "body": "..."}`` or
    ``{"type": "image", "url": "...", "caption": "..."}``.
    """

    for part in messages:
        kind = part.get("type")
        if kind == "image":
            send_whatsapp_image(
                to_phone,
                str(part.get("url") or ""),
                caption=str(part.get("caption") or ""),
            )
        else:
            send_whatsapp_text(to_phone, str(part.get("body") or ""))


def verify_webhook_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """Validate ``X-Hub-Signature-256`` when ``WHATSAPP_APP_SECRET`` is set.

    Args:
        raw_body: Exact request body bytes.
        signature_header: Header value like ``sha256=...``.

    Returns:
        True if signature is valid, or if no app secret is configured
        (dev-friendly). False when a secret is set and the signature fails.
    """

    if not WHATSAPP_APP_SECRET:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        WHATSAPP_APP_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    received = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)


def extract_inbound_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Pull text messages from a WhatsApp Cloud API webhook payload.

    Returns:
        A list of ``{"from": "...", "text": "...", "message_id": "..."}``.
    """

    results: list[dict[str, str]] = []
    entries = payload.get("entry")
    if not isinstance(entries, list):
        return results
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes")
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            messages = value.get("messages")
            if not isinstance(messages, list):
                continue
            for message in messages:
                if not isinstance(message, dict):
                    continue
                if message.get("type") != "text":
                    continue
                text_obj = message.get("text")
                body = ""
                if isinstance(text_obj, dict):
                    body = str(text_obj.get("body") or "")
                sender = str(message.get("from") or "")
                msg_id = str(message.get("id") or "")
                if sender and body.strip():
                    results.append(
                        {
                            "from": sender,
                            "text": body.strip(),
                            "message_id": msg_id,
                        }
                    )
    return results
