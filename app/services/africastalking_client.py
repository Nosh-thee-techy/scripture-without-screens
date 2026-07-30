"""Africa's Talking messaging and voice service wrapper."""

from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

import africastalking

from app.config import AT_API_KEY, AT_USERNAME


class AfricasTalkingError(RuntimeError):
    """Raised when Africa's Talking cannot accept an outbound request."""


def _serialize_voice_response(root: Element) -> str:
    """Serialize an Africa's Talking voice action tree as XML.

    Args:
        root: Root ``Response`` XML element containing voice actions.

    Returns:
        A UTF-8-declared XML document.
    """

    xml_body = tostring(root, encoding="unicode", short_empty_elements=True)
    return f'<?xml version="1.0" encoding="UTF-8"?>{xml_body}'


def build_voice_say_response(message: str) -> str:
    """Build XML that reads one message aloud and ends the call flow.

    Args:
        message: Plain text Africa's Talking should synthesize as speech.

    Returns:
        An escaped Africa's Talking ``Response`` XML document.

    Raises:
        ValueError: If ``message`` is blank.
    """

    if not message.strip():
        raise ValueError("message must not be blank")

    root = Element("Response")
    say = SubElement(root, "Say")
    say.text = " ".join(message.split())
    return _serialize_voice_response(root)


def build_voice_play_response(audio_url: str, fallback_text: str = "") -> str:
    """Build XML that plays a hosted audio file, with optional Say fallback.

    Args:
        audio_url: Public HTTPS URL Africa's Talking can fetch (often ngrok).
        fallback_text: Optional text spoken if Play is insufficient alone.

    Returns:
        An escaped Africa's Talking ``Response`` XML document.

    Raises:
        ValueError: If ``audio_url`` is blank.
    """

    if not audio_url.strip():
        raise ValueError("audio_url must not be blank")

    root = Element("Response")
    play = SubElement(root, "Play")
    play.text = audio_url.strip()
    if fallback_text.strip():
        # Keep a short spoken cue after audio for callers on weak networks.
        say = SubElement(root, "Say")
        say.text = " ".join(fallback_text.split())
    return _serialize_voice_response(root)


def build_voice_menu_response(prompt: str) -> str:
    """Build XML that speaks a menu and collects one keypad digit.

    Args:
        prompt: Instructions to read before waiting for keypad input.

    Returns:
        An escaped Africa's Talking XML document containing ``GetDigits``.

    Raises:
        ValueError: If ``prompt`` is blank.
    """

    if not prompt.strip():
        raise ValueError("prompt must not be blank")

    root = Element("Response")
    get_digits = SubElement(
        root,
        "GetDigits",
        {"numDigits": "1", "timeout": "15", "finishOnKey": "#"},
    )
    say = SubElement(get_digits, "Say")
    say.text = " ".join(prompt.split())
    return _serialize_voice_response(root)


def _get_sms_service() -> Any:
    """Initialize the SDK and return its SMS service.

    Returns:
        The configured Africa's Talking SMS service object.

    Raises:
        AfricasTalkingError: If required credentials are missing or SDK
            initialization fails.
    """

    if not AT_USERNAME or not AT_API_KEY:
        raise AfricasTalkingError(
            "AT_USERNAME and AT_API_KEY must be configured."
        )

    try:
        africastalking.initialize(AT_USERNAME, AT_API_KEY)
        return africastalking.SMS
    except Exception as exc:
        # The third-party SDK does not expose one stable base exception across
        # versions, so convert initialization errors into an app-level error.
        raise AfricasTalkingError(
            "Could not initialize Africa's Talking."
        ) from exc


def send_sms(
    message: str, recipient: str, sender_id: str | None = None
) -> dict[str, Any]:
    """Send one SMS through Africa's Talking.

    Args:
        message: Text to send to the subscriber.
        recipient: Destination phone number in international format.
        sender_id: Optional registered shortcode or alphanumeric sender.

    Returns:
        The decoded response dictionary from the Africa's Talking SDK.

    Raises:
        ValueError: If the message or recipient is blank.
        AfricasTalkingError: If configuration or delivery submission fails.
    """

    if not message.strip():
        raise ValueError("message must not be blank")
    if not recipient.strip():
        raise ValueError("recipient must not be blank")

    sms_service = _get_sms_service()
    try:
        response = sms_service.send(
            message,
            [recipient],
            sender_id=sender_id or None,
        )
    except Exception as exc:
        # Normalize network errors and SDK-specific exceptions so route code
        # only needs to handle one integration failure type.
        raise AfricasTalkingError(
            "Africa's Talking could not submit the SMS."
        ) from exc

    if not isinstance(response, dict):
        raise AfricasTalkingError(
            "Africa's Talking returned an unexpected SMS response."
        )
    return response
