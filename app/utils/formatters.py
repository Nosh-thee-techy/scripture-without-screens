"""Text formatting helpers for feature-phone channels."""


SMS_CHARACTER_LIMIT = 160
USSD_RESPONSE_LIMIT = 160
USSD_CONTROL_PREFIX_LENGTH = len("END ")


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """Normalize and shorten text without cutting a word when possible.

    Args:
        text: Plain text to prepare for phone delivery.
        max_length: Maximum number of characters in the returned text.
        suffix: Marker appended when truncation is required.

    Returns:
        Whitespace-normalized text no longer than ``max_length`` characters.

    Raises:
        ValueError: If the limit cannot contain the truncation suffix.
    """

    if max_length < len(suffix):
        raise ValueError("max_length must be at least as long as suffix")

    normalized = " ".join(text.split())
    if len(normalized) <= max_length:
        return normalized

    available_length = max_length - len(suffix)
    shortened = normalized[:available_length].rsplit(" ", 1)[0]
    if not shortened:
        shortened = normalized[:available_length]
    return f"{shortened}{suffix}"


def format_for_sms(text: str) -> str:
    """Format text as a single SMS-sized message.

    Args:
        text: Plain text to send by SMS.

    Returns:
        Normalized text of at most 160 characters.
    """

    # Three ASCII periods preserve GSM-7 compatibility better than a Unicode
    # ellipsis when the rest of the message also uses GSM-7 characters.
    return truncate_text(text, SMS_CHARACTER_LIMIT)


def format_for_ussd(text: str) -> str:
    """Format content so its complete ``END`` response fits 160 characters.

    Args:
        text: Plain text to display before the USSD session closes.

    Returns:
        Normalized text sized to leave room for Africa's Talking's ``END ``
        control prefix.
    """

    content_limit = USSD_RESPONSE_LIMIT - USSD_CONTROL_PREFIX_LENGTH
    return truncate_text(text, content_limit)
