"""Meta WhatsApp Cloud API webhook (verify + conversational menus)."""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse

from app.config import (
    WHATSAPP_BUSINESS_ACCOUNT_ID,
    WHATSAPP_PHONE_NUMBER_ID,
    WHATSAPP_VERIFY_TOKEN,
)
from app.services.kids_ai import (
    explain_scripture,
    explain_votd_for_kid,
    kids_affirmation,
    kids_prayer,
    simplify_for_kid,
    translate_line,
    write_prayer,
)
from app.services.kids_content import (
    AGE_BANDS,
    get_kids_plan,
    get_kids_plan_day,
    get_quiz_questions,
    get_section,
    get_story,
    kids_plan_day_count,
    list_plan_topics,
    list_stories_for_age,
    passage_image_url,
    section_count,
    story_image_url,
    topic_label,
)
from app.services.usfm import book_title, chapter_passage_id, parse_usfm
from app.services.whatsapp_client import (
    WhatsAppError,
    extract_inbound_messages,
    send_whatsapp_messages,
    send_whatsapp_text,
    verify_webhook_signature,
    whatsapp_configured,
)
from app.services.youversion_client import (
    SUPPORTED_LANGUAGES,
    YouVersionError,
    get_book_chapter_count,
    get_passage_detail,
    get_verse_of_the_day_detail,
    list_bibles,
    list_books,
    prefer_bible_id,
)
from app.utils.i18n import LANGUAGE_NATIVE_LABELS, main_menu, t
from app.utils.session_store import get_user_session, update_user_session


logger = logging.getLogger(__name__)

router = APIRouter(tags=["whatsapp"])

# WhatsApp allows long messages; keep readable bubbles.
_WA_MAX = 1400

WaOut = str | list[dict[str, Any]]


def _text(body: str) -> list[dict[str, Any]]:
    return [{"type": "text", "body": body}]


def _image(url: str, caption: str = "") -> list[dict[str, Any]]:
    return [{"type": "image", "url": url, "caption": caption}]


def _out(*parts: WaOut) -> list[dict[str, Any]]:
    """Flatten text/image parts into one outbound list."""

    messages: list[dict[str, Any]] = []
    for part in parts:
        if isinstance(part, str):
            if part.strip():
                messages.append({"type": "text", "body": part})
        else:
            messages.extend(part)
    return messages


def _normalize_phone(raw: str) -> str:
    """Store WhatsApp senders as ``+`` international MSISDNs."""

    digits = raw.strip().lstrip("+")
    return f"+{digits}" if digits else raw


def _clip(text: str, max_chars: int = _WA_MAX) -> str:
    """Trim long WhatsApp bodies; keep line breaks for menus and verses."""

    # Collapse runs of spaces/tabs but preserve newlines for readability.
    lines = [" ".join(line.split()) for line in text.replace("\r\n", "\n").split("\n")]
    normalized = "\n".join(line for line in lines if line is not None)
    if len(normalized) <= max_chars:
        return normalized
    shortened = normalized[: max_chars - 3].rsplit(" ", 1)[0]
    if not shortened:
        shortened = normalized[: max_chars - 3]
    return f"{shortened}..."


def _lang(session: dict[str, Any]) -> str:
    return str(session.get("language") or "en")


def _set_wa(phone: str, flow: str, **fields: Any) -> dict[str, Any]:
    return update_user_session(phone, wa_flow=flow, **fields)


def _menu(language: str) -> str:
    return (
        f"{main_menu(language)}\n\n"
        f"{t(language, 'wa_hint')}"
    )


def _votd_actions(language: str) -> str:
    return "\n".join(
        [
            f"1. {t(language, 'votd_explain')}",
            f"2. {t(language, 'votd_pray')}",
            f"3. {t(language, 'votd_chapter')}",
            f"4. {t(language, 'votd_compare')}",
            f"0. {t(language, 'home')}",
        ]
    )


def _open_votd(phone: str, session: dict[str, Any]) -> str:
    """Show VOTD verse plus explain / pray / chapter / compare choices."""

    language = _lang(session)
    try:
        detail = get_verse_of_the_day_detail(
            language=language, bible_id=session.get("bible_id")
        )
    except YouVersionError:
        return t(language, "votd_unavailable")

    _set_wa(
        phone,
        "votd",
        votd_passage_id=detail["passage_id"],
        kids_votd_ref=detail["reference"],
        kids_votd_text=detail["text"],
    )
    body = _clip(f"{detail['reference']}\n{detail['text']}")
    return f"{body}\n\n{_votd_actions(language)}"


def _compare_versions(
    passage_id: str, language: str, preferred_bible_id: Any
) -> str:
    """Show the same passage in up to three licensed Bible versions."""

    try:
        bibles = list_bibles(language, limit=3)
    except YouVersionError:
        return t(language, "versions_fail")

    # Prefer the subscriber's saved Bible first in the list.
    if isinstance(preferred_bible_id, int):
        bibles = sorted(
            bibles,
            key=lambda row: 0 if row["id"] == preferred_bible_id else 1,
        )

    blocks: list[str] = [t(language, "votd_compare_title")]
    for bible in bibles[:3]:
        try:
            detail = get_passage_detail(
                passage_id, language=language, bible_id=bible["id"]
            )
            snippet = _clip(detail["text"], 280)
            blocks.append(f"*{bible['abbreviation']}*\n{snippet}")
        except YouVersionError:
            blocks.append(
                f"*{bible['abbreviation']}*\n{t(language, 'verse_unavailable')}"
            )
    return _clip("\n\n".join(blocks))


def _handle_votd(phone: str, session: dict[str, Any], action: str) -> str:
    language = _lang(session)
    passage_id = str(session.get("votd_passage_id") or "")
    reference = str(session.get("kids_votd_ref") or "")
    verse_text = str(session.get("kids_votd_text") or "")

    if action in {"0", "MENU", "HOME"}:
        _set_wa(phone, "main")
        return _menu(language)

    if not passage_id:
        return _open_votd(phone, session)

    if action == "1":
        explanation = explain_scripture(
            reference, verse_text, language=language, max_chars=500
        )
        return (
            f"{_clip(explanation)}\n\n"
            f"1. {t(language, 'votd_explain_again')}\n"
            f"2. {t(language, 'votd_pray')}\n"
            f"3. {t(language, 'votd_chapter')}\n"
            f"4. {t(language, 'votd_compare')}\n"
            f"0. {t(language, 'home')}"
        )

    if action == "2":
        prayer = write_prayer(
            reference, verse_text, language=language, max_chars=500
        )
        return (
            f"{_clip(prayer)}\n\n"
            f"1. {t(language, 'votd_explain')}\n"
            f"2. {t(language, 'votd_pray_again')}\n"
            f"3. {t(language, 'votd_chapter')}\n"
            f"4. {t(language, 'votd_compare')}\n"
            f"0. {t(language, 'home')}"
        )

    if action == "3":
        book, chapter, _verse = parse_usfm(passage_id)
        if not book or not chapter:
            return t(language, "chapter_unavailable")
        try:
            detail = get_passage_detail(
                chapter_passage_id(book, chapter),
                language=language,
                bible_id=session.get("bible_id"),
            )
        except YouVersionError:
            return t(language, "chapter_load_fail")
        body = _clip(f"{detail['reference']}\n{detail['text']}")
        return (
            f"{body}\n\n"
            f"{_votd_actions(language)}"
        )

    if action == "4":
        comparison = _compare_versions(
            passage_id, language, session.get("bible_id")
        )
        return f"{comparison}\n\n{_votd_actions(language)}"

    # Unknown digit — reshow verse + options instead of a confusing help dump.
    return (
        f"{reference}\n{_clip(verse_text, 400)}\n\n{_votd_actions(language)}"
    )


def _open_bible_root(phone: str, language: str) -> str:
    _set_wa(phone, "bible_root")
    return (
        f"{t(language, 'read_bible_title')}\n"
        f"1. {t(language, 'read_ot')}\n"
        f"2. {t(language, 'read_nt')}\n"
        f"0. {t(language, 'home')}"
    )


def _books_list(phone: str, session: dict[str, Any], testament: str) -> str:
    language = _lang(session)
    try:
        books = list_books(
            language, bible_id=session.get("bible_id"), testament=testament
        )
    except YouVersionError:
        return t(language, "books_fail")

    page = int(session.get("read_book_page") or 0)
    per_page = 8
    start = page * per_page
    chunk = books[start : start + per_page]
    heading = t(language, "books_ot" if testament == "old" else "books_nt")
    lines = [heading]
    for index, book in enumerate(chunk, start=1):
        lines.append(f"{index}. {book['title']}")
    if start + per_page < len(books):
        lines.append(f"9. {t(language, 'more_books')}")
    if page > 0:
        lines.append(f"7. {t(language, 'previous')}")
    lines.append(f"0. {t(language, 'home')}")
    _set_wa(
        phone,
        "bible_books",
        read_testament=testament,
        read_book_page=page,
        wa_books_cache=[b["id"] for b in books],
    )
    return "\n".join(lines)


def _handle_bible_root(phone: str, session: dict[str, Any], action: str) -> str:
    language = _lang(session)
    if action in {"0", "MENU"}:
        _set_wa(phone, "main")
        return _menu(language)
    if action == "1":
        return _books_list(phone, session, "old")
    if action == "2":
        return _books_list(phone, session, "new")
    return _open_bible_root(phone, language)


def _handle_bible_books(phone: str, session: dict[str, Any], action: str) -> str:
    language = _lang(session)
    testament = str(session.get("read_testament") or "old")
    if action in {"0", "MENU"}:
        _set_wa(phone, "main")
        return _menu(language)
    if action == "9":
        page = int(session.get("read_book_page") or 0) + 1
        session = _set_wa(phone, "bible_books", read_book_page=page)
        return _books_list(phone, session, testament)
    if action == "7":
        page = max(0, int(session.get("read_book_page") or 0) - 1)
        session = _set_wa(phone, "bible_books", read_book_page=page)
        return _books_list(phone, session, testament)
    try:
        choice = int(action)
    except ValueError:
        return _books_list(phone, session, testament)
    if choice < 1 or choice > 8:
        return _books_list(phone, session, testament)

    try:
        books = list_books(
            language, bible_id=session.get("bible_id"), testament=testament
        )
    except YouVersionError:
        return t(language, "books_fail")
    page = int(session.get("read_book_page") or 0)
    index = page * 8 + (choice - 1)
    if index < 0 or index >= len(books):
        return _books_list(phone, session, testament)
    book = books[index]
    _set_wa(phone, "bible_chapter_pick", read_book=book["id"], read_chapter=1)
    try:
        total = get_book_chapter_count(
            book["id"], language=language, bible_id=session.get("bible_id")
        )
    except YouVersionError:
        total = 1
    return (
        f"{book['title']}\n"
        f"{t(language, 'wa_enter_chapter', total=total)}\n"
        f"0. {t(language, 'home')}"
    )


def _handle_bible_chapter_pick(
    phone: str, session: dict[str, Any], action: str
) -> str:
    language = _lang(session)
    book = str(session.get("read_book") or "GEN")
    if action in {"0", "MENU"}:
        _set_wa(phone, "main")
        return _menu(language)
    try:
        chapter = int(action)
    except ValueError:
        return (
            f"{t(language, 'wa_enter_chapter', total='?')}\n"
            f"0. {t(language, 'home')}"
        )
    try:
        total = get_book_chapter_count(
            book, language=language, bible_id=session.get("bible_id")
        )
    except YouVersionError:
        return t(language, "chapters_fail")
    if chapter < 1 or chapter > total:
        return (
            f"{t(language, 'wa_enter_chapter', total=total)}\n"
            f"0. {t(language, 'home')}"
        )
    try:
        detail = get_passage_detail(
            chapter_passage_id(book, chapter),
            language=language,
            bible_id=session.get("bible_id"),
        )
    except YouVersionError:
        return t(language, "chapter_load_fail")
    _set_wa(phone, "bible_read", read_chapter=chapter)
    body = _clip(f"{detail['reference']}\n{detail['text']}")
    return (
        f"{body}\n\n"
        f"1. {t(language, 'next_chapter')}\n"
        f"2. {t(language, 'pray_option')}\n"
        f"0. {t(language, 'home')}"
    )


def _handle_bible_read(phone: str, session: dict[str, Any], action: str) -> str:
    language = _lang(session)
    book = str(session.get("read_book") or "GEN")
    chapter = int(session.get("read_chapter") or 1)
    if action in {"0", "MENU"}:
        _set_wa(phone, "main")
        return _menu(language)
    if action == "2":
        try:
            detail = get_passage_detail(
                chapter_passage_id(book, chapter),
                language=language,
                bible_id=session.get("bible_id"),
            )
        except YouVersionError:
            return t(language, "chapter_load_fail")
        prayer = write_prayer(
            detail["reference"], detail["text"], language=language, max_chars=500
        )
        return (
            f"{_clip(prayer)}\n\n"
            f"1. {t(language, 'next_chapter')}\n"
            f"0. {t(language, 'home')}"
        )
    if action == "1":
        try:
            total = get_book_chapter_count(
                book, language=language, bible_id=session.get("bible_id")
            )
        except YouVersionError:
            return t(language, "chapter_load_fail")
        if chapter >= total:
            _set_wa(phone, "main")
            return (
                f"{t(language, 'book_done', book=book_title(book))}\n\n"
                f"{_menu(language)}"
            )
        next_chapter = chapter + 1
        try:
            detail = get_passage_detail(
                chapter_passage_id(book, next_chapter),
                language=language,
                bible_id=session.get("bible_id"),
            )
        except YouVersionError:
            return t(language, "chapter_load_fail")
        _set_wa(phone, "bible_read", read_chapter=next_chapter)
        body = _clip(f"{detail['reference']}\n{detail['text']}")
        return (
            f"{body}\n\n"
            f"1. {t(language, 'next_chapter')}\n"
            f"2. {t(language, 'pray_option')}\n"
            f"0. {t(language, 'home')}"
        )
    # Reshow current chapter with options.
    return _handle_bible_chapter_pick(phone, session, str(chapter))


def _handle_version(phone: str, session: dict[str, Any], action: str) -> str:
    language = _lang(session)
    if action in {"0", "MENU", "9"}:
        _set_wa(phone, "main")
        return _menu(language)
    try:
        bibles = list_bibles(language, limit=5)
    except YouVersionError:
        return t(language, "versions_fail")
    try:
        choice = int(action)
    except ValueError:
        lines = [t(language, "choose_version")]
        for index, bible in enumerate(bibles, start=1):
            lines.append(f"{index}. {bible['abbreviation']} — {bible['title']}")
        lines.append(f"0. {t(language, 'home')}")
        return "\n".join(lines)
    if choice < 1 or choice > len(bibles):
        return _handle_version(phone, session, "")
    selected = bibles[choice - 1]
    _set_wa(phone, "main", bible_id=selected["id"])
    return (
        f"{t(language, 'bible_set', abbr=selected['abbreviation'])}\n\n"
        f"{_menu(language)}"
    )


def _handle_lang_picker(phone: str, session: dict[str, Any], action: str) -> str:
    if action in {"0", "MENU"} and session.get("language_set"):
        _set_wa(phone, "main")
        return _menu(_lang(session))
    try:
        index = int(action)
    except ValueError:
        lines = [t(_lang(session) if session.get("language_set") else "en", "choose_language")]
        for i, (code, _label) in enumerate(SUPPORTED_LANGUAGES, start=1):
            lines.append(f"{i}. {LANGUAGE_NATIVE_LABELS.get(code, code)}")
        if session.get("language_set"):
            lines.append(f"0. {t(_lang(session), 'home')}")
        return "\n".join(lines)
    if index < 1 or index > len(SUPPORTED_LANGUAGES):
        return _handle_lang_picker(phone, session, "")
    code, _label = SUPPORTED_LANGUAGES[index - 1]
    native = LANGUAGE_NATIVE_LABELS.get(code, code)
    _set_wa(
        phone,
        "main",
        language=code,
        language_set=True,
        bible_id=None,
        sms_daily=True,
    )
    return f"{t(code, 'language_set', label=native)}\n\n{_menu(code)}"


def _handle_main(phone: str, session: dict[str, Any], action: str) -> str:
    language = _lang(session)
    upper = action.upper()

    if upper in {"MENU", "HOME", "0", "HI", "HELLO", "START", "HELP"}:
        _set_wa(phone, "main")
        return _menu(language)

    if upper == "VOTD":
        return _open_votd(phone, session)

    lang_aliases = {
        "EN": "en",
        "SW": "sw",
        "KISWAHILI": "sw",
        "KI": "ki",
        "LUO": "luo",
        "GAX": "gax",
        "BORANA": "gax",
        "OROM": "gax",
    }
    if upper in lang_aliases:
        code = lang_aliases[upper]
        native = LANGUAGE_NATIVE_LABELS.get(code, code)
        _set_wa(phone, "main", language=code, language_set=True)
        return f"{t(code, 'language_set', label=native)}\n\n{_menu(code)}"

    if action == "1":
        return _open_votd(phone, session)
    if action == "2":
        return _open_bible_root(phone, language)
    if action == "3":
        _set_wa(phone, "main")
        return (
            f"{t(language, 'wa_plan_hint')}\n\n"
            f"{_menu(language)}"
        )
    if action == "4":
        return _enter_kids_wa(phone, session)
    if action == "5":
        _set_wa(phone, "version")
        return _handle_version(phone, session, "")
    if action == "6":
        _set_wa(phone, "lang")
        return _handle_lang_picker(phone, session, "")

    # Unknown text — reshow the numbered menu (never the first-chat help dump).
    return _menu(language)


def _kids_hub(language: str) -> str:
    return "\n".join(
        [
            t(language, "kids_hub"),
            f"1. {t(language, 'kids_menu_votd')}",
            f"2. {t(language, 'kids_menu_stories')}",
            f"3. {t(language, 'kids_menu_plans')}",
            f"0. {t(language, 'home')}",
        ]
    )


def _enter_kids_wa(phone: str, session: dict[str, Any]) -> WaOut:
    language = _lang(session)
    if not session.get("age_band"):
        _set_wa(phone, "kids_age")
        lines = [t(language, "kids_age")]
        for index, (code, _label) in enumerate(AGE_BANDS, start=1):
            lines.append(f"{index}. {t(language, f'age_{code}')}")
        lines.append(f"0. {t(language, 'home')}")
        return "\n".join(lines)
    _set_wa(phone, "kids_hub")
    return _kids_hub(language)


def _present_kids_section_wa(phone: str, session: dict[str, Any]) -> WaOut:
    """Send story visual + section text + Got it / simpler choices."""

    language = _lang(session)
    age_band = str(session.get("age_band") or "6_9")
    story_id = str(session.get("kids_story_id") or "")
    section_index = int(session.get("kids_section") or 0)
    try:
        story = get_story(story_id)
        english = get_section(story_id, section_index)
    except ValueError:
        _set_wa(phone, "kids_hub")
        return _kids_hub(language)

    display = translate_line(english, language=language, age_band=age_band)
    total = section_count(story_id)
    _set_wa(phone, "kids_got_it")
    body = (
        f"{story['title']} ({section_index + 1}/{total})\n"
        f"{display}\n\n"
        f"1. {t(language, 'got_it')}\n"
        f"2. {t(language, 'explain_simpler')}\n"
        f"0. {t(language, 'home')}"
    )
    image = story_image_url(story_id)
    if image:
        return _out(
            _image(image, caption=_clip(story["title"], 200)),
            body,
        )
    return body


def _handle_kids_age(phone: str, session: dict[str, Any], action: str) -> WaOut:
    language = _lang(session)
    if action in {"0", "MENU"}:
        _set_wa(phone, "main")
        return _menu(language)
    try:
        choice = int(action)
    except ValueError:
        return _enter_kids_wa(phone, {**session, "age_band": None})
    if choice < 1 or choice > len(AGE_BANDS):
        return _enter_kids_wa(phone, {**session, "age_band": None})
    age_code, _label = AGE_BANDS[choice - 1]
    session = _set_wa(phone, "kids_hub", age_band=age_code)
    return _kids_hub(language)


def _handle_kids_hub(phone: str, session: dict[str, Any], action: str) -> WaOut:
    language = _lang(session)
    if action in {"0", "MENU"}:
        _set_wa(phone, "main")
        return _menu(language)
    if action == "1":
        return _open_kids_votd_wa(phone, session)
    if action == "2":
        _set_wa(phone, "kids_testament")
        return (
            f"{t(language, 'kids_pick_testament')}\n"
            f"1. {t(language, 'read_ot')}\n"
            f"2. {t(language, 'read_nt')}\n"
            f"0. {t(language, 'home')}"
        )
    if action == "3":
        _set_wa(phone, "kids_plans")
        lines = [t(language, "kids_plans_title")]
        for index, (code, _label) in enumerate(list_plan_topics(), start=1):
            lines.append(f"{index}. {t(language, f'kids_plan_{code}')}")
        lines.append(f"0. {t(language, 'home')}")
        return "\n".join(lines)
    return _kids_hub(language)


def _kids_bible_id(session: dict[str, Any], language: str) -> int | None:
    """Prefer NIV (simple + accurate) for kids English; else session/default."""

    fallback = session.get("bible_id")
    fallback_id = fallback if isinstance(fallback, int) else None
    if language in {"en", "eng"}:
        return prefer_bible_id(
            language, abbreviations=("NIV11", "NIV", "NIrV"), fallback=fallback_id
        )
    return prefer_bible_id(
        language,
        abbreviations=("NIV", "NIrV", "BSB"),
        fallback=fallback_id,
    )


def _open_kids_votd_wa(phone: str, session: dict[str, Any]) -> WaOut:
    language = _lang(session)
    age_band = str(session.get("age_band") or "6_9")
    bible_id = _kids_bible_id(session, language)
    try:
        detail = get_verse_of_the_day_detail(language=language, bible_id=bible_id)
    except YouVersionError:
        return t(language, "votd_unavailable")

    version_label = "NIV"
    try:
        for bible in list_bibles(language, limit=20):
            if bible.get("id") == bible_id:
                raw = str(bible.get("abbreviation") or "NIV")
                version_label = "NIV" if "niv" in raw.lower() else raw
                break
    except YouVersionError:
        pass

    explanation = explain_votd_for_kid(
        detail["reference"],
        detail["text"],
        language=language,
        age_band=age_band,
        max_chars=700,
    )
    _set_wa(
        phone,
        "kids_votd",
        votd_passage_id=detail["passage_id"],
        kids_votd_ref=detail["reference"],
        kids_votd_text=detail["text"],
        kids_close_step="choose",
    )
    visual = passage_image_url(
        detail["reference"], detail["text"], detail["passage_id"]
    )
    body = (
        f"{detail['reference']} ({version_label})\n"
        f"{detail['text']}\n\n"
        f"{explanation}\n\n"
        f"1. {t(language, 'kids_pray')}\n"
        f"2. {t(language, 'kids_affirm')}\n"
        f"0. {t(language, 'home')}"
    )
    if visual:
        return _out(_image(visual, caption=detail["reference"]), body)
    return body


def _handle_kids_votd(phone: str, session: dict[str, Any], action: str) -> WaOut:
    language = _lang(session)
    age_band = str(session.get("age_band") or "6_9")
    reference = str(session.get("kids_votd_ref") or "Verse")
    verse_text = str(session.get("kids_votd_text") or "")
    topic = f"{reference}: {verse_text}"
    step = str(session.get("kids_close_step") or "choose")
    if action in {"0", "MENU"}:
        _set_wa(phone, "kids_hub", kids_close_step=None)
        return _kids_hub(language)

    def _affirm() -> str:
        affirmation = kids_affirmation(
            topic, language=language, age_band=age_band, max_chars=400
        )
        _set_wa(phone, "kids_hub", kids_close_step=None)
        return f"{affirmation}\n\n{_kids_hub(language)}"

    if step == "after_prayer":
        if action == "1":
            return _affirm()
        return (
            f"1. {t(language, 'kids_affirm')}\n"
            f"0. {t(language, 'home')}"
        )
    if action == "2":
        return _affirm()
    if action == "1":
        prayer = kids_prayer(topic, language=language, age_band=age_band, max_chars=400)
        _set_wa(phone, "kids_votd", kids_close_step="after_prayer")
        return (
            f"{prayer}\n\n"
            f"1. {t(language, 'kids_affirm')}\n"
            f"0. {t(language, 'home')}"
        )
    return _open_kids_votd_wa(phone, session)


def _handle_kids_testament(
    phone: str, session: dict[str, Any], action: str
) -> WaOut:
    language = _lang(session)
    if action in {"0", "MENU"}:
        _set_wa(phone, "kids_hub")
        return _kids_hub(language)
    if action == "1":
        session = _set_wa(phone, "kids_stories", kids_testament="old")
        return _story_picker_wa(session)
    if action == "2":
        session = _set_wa(phone, "kids_stories", kids_testament="new")
        return _story_picker_wa(session)
    return (
        f"{t(language, 'kids_pick_testament')}\n"
        f"1. {t(language, 'read_ot')}\n"
        f"2. {t(language, 'read_nt')}\n"
        f"0. {t(language, 'home')}"
    )


def _story_picker_wa(session: dict[str, Any]) -> str:
    language = _lang(session)
    age_band = str(session.get("age_band") or "6_9")
    testament = str(session.get("kids_testament") or "old")
    stories = list_stories_for_age(age_band, testament=testament)
    heading = t(
        language, "kids_stories_ot" if testament == "old" else "kids_stories_nt"
    )
    lines = [heading, t(language, "wa_kids_pick_story")]
    for index, story in enumerate(stories, start=1):
        lines.append(f"{index}. {story['title']}")
    lines.append(f"0. {t(language, 'home')}")
    return "\n".join(lines)


def _handle_kids_stories(
    phone: str, session: dict[str, Any], action: str
) -> WaOut:
    language = _lang(session)
    if action in {"0", "MENU"}:
        _set_wa(phone, "kids_hub")
        return _kids_hub(language)
    age_band = str(session.get("age_band") or "6_9")
    testament = str(session.get("kids_testament") or "old")
    stories = list_stories_for_age(age_band, testament=testament)
    try:
        choice = int(action)
    except ValueError:
        return _story_picker_wa(session)
    if choice < 1 or choice > len(stories):
        return _story_picker_wa(session)
    story = stories[choice - 1]
    session = _set_wa(
        phone,
        "kids_got_it",
        kids_story_id=story["id"],
        kids_section=0,
        kids_quiz_index=0,
        kids_quiz_retries=0,
    )
    return _present_kids_section_wa(phone, session)


def _handle_kids_got_it(
    phone: str, session: dict[str, Any], action: str
) -> WaOut:
    language = _lang(session)
    age_band = str(session.get("age_band") or "6_9")
    story_id = str(session.get("kids_story_id") or "")
    section_index = int(session.get("kids_section") or 0)
    if action in {"0", "MENU"}:
        _set_wa(phone, "kids_hub")
        return _kids_hub(language)
    if action == "2":
        try:
            english = get_section(story_id, section_index)
        except ValueError:
            return _enter_kids_wa(phone, session)
        simpler = simplify_for_kid(
            english, language=language, age_band=age_band, max_chars=400
        )
        image = story_image_url(story_id)
        body = (
            f"{simpler}\n\n"
            f"1. {t(language, 'got_it')}\n"
            f"2. {t(language, 'explain_simpler')}\n"
            f"0. {t(language, 'home')}"
        )
        if image:
            return _out(_image(image, caption=t(language, "explain_simpler")), body)
        return body
    if action == "1":
        total = section_count(story_id)
        next_index = section_index + 1
        if next_index >= total:
            return _start_kids_quiz_wa(phone, session)
        session = _set_wa(phone, "kids_got_it", kids_section=next_index)
        return _present_kids_section_wa(phone, session)
    return _present_kids_section_wa(phone, session)


def _start_kids_quiz_wa(phone: str, session: dict[str, Any]) -> WaOut:
    session = _set_wa(
        phone, "kids_quiz", kids_quiz_index=0, kids_quiz_retries=0
    )
    return _quiz_prompt_wa(session)


def _quiz_prompt_wa(session: dict[str, Any]) -> str:
    language = _lang(session)
    story_id = str(session.get("kids_story_id") or "")
    age_band = str(session.get("age_band") or "6_9")
    index = int(session.get("kids_quiz_index") or 0)
    questions = get_quiz_questions(story_id, age_band)
    if index >= len(questions):
        return t(language, "amazing_done")
    question = questions[index]
    lines = [
        t(
            language,
            "quiz_line",
            n=index + 1,
            total=len(questions),
            q=question["q"],
        )
    ]
    for choice_index, choice in enumerate(question["choices"], start=1):
        lines.append(f"{choice_index}. {choice}")
    lines.append(f"0. {t(language, 'home')}")
    return "\n".join(lines)


def _offer_kids_close_wa(
    phone: str, session: dict[str, Any], intro_key: str, **kwargs: Any
) -> WaOut:
    language = _lang(session)
    story_id = str(session.get("kids_story_id") or "")
    intro = t(language, intro_key, **kwargs)
    _set_wa(
        phone,
        "kids_close",
        kids_close_step="choose",
        kids_quiz_index=0,
        kids_quiz_retries=0,
    )
    body = (
        f"{intro}\n\n"
        f"1. {t(language, 'kids_pray')}\n"
        f"2. {t(language, 'kids_affirm')}\n"
        f"0. {t(language, 'home')}"
    )
    image = story_image_url(story_id)
    if image:
        return _out(_image(image, caption=_clip(intro, 180)), body)
    return body


def _handle_kids_quiz(phone: str, session: dict[str, Any], action: str) -> WaOut:
    language = _lang(session)
    if action in {"0", "MENU"}:
        _set_wa(phone, "kids_hub")
        return _kids_hub(language)
    story_id = str(session.get("kids_story_id") or "")
    age_band = str(session.get("age_band") or "6_9")
    index = int(session.get("kids_quiz_index") or 0)
    retries = int(session.get("kids_quiz_retries") or 0)
    questions = get_quiz_questions(story_id, age_band)
    if index >= len(questions):
        return _offer_kids_close_wa(phone, session, "amazing_done")
    question = questions[index]
    try:
        choice = int(action)
    except ValueError:
        return _quiz_prompt_wa(session)
    if choice < 1 or choice > len(question["choices"]):
        return _quiz_prompt_wa(session)
    if choice == int(question["answer"]):
        next_q = index + 1
        if next_q >= len(questions):
            return _offer_kids_close_wa(phone, session, "quiz_finished")
        session = _set_wa(
            phone, "kids_quiz", kids_quiz_index=next_q, kids_quiz_retries=0
        )
        return _quiz_prompt_wa(session)
    if retries < 1:
        _set_wa(phone, "kids_quiz", kids_quiz_retries=retries + 1)
        hint = question.get("hint") or "Try again!"
        return (
            f"{t(language, 'almost', hint=hint)}\n"
            + "\n".join(
                f"{i}. {c}" for i, c in enumerate(question["choices"], start=1)
            )
        )
    correct = question["choices"][int(question["answer"]) - 1]
    next_q = index + 1
    if next_q >= len(questions):
        return _offer_kids_close_wa(
            phone, session, "story_done", answer=correct
        )
    session = _set_wa(
        phone, "kids_quiz", kids_quiz_index=next_q, kids_quiz_retries=0
    )
    return (
        f"{t(language, 'answer_was', answer=correct)}\n"
        f"{_quiz_prompt_wa(session)}"
    )


def _handle_kids_close(phone: str, session: dict[str, Any], action: str) -> WaOut:
    language = _lang(session)
    age_band = str(session.get("age_band") or "6_9")
    story_id = str(session.get("kids_story_id") or "")
    try:
        title = get_story(story_id)["title"]
    except ValueError:
        title = "this story"
    step = str(session.get("kids_close_step") or "choose")
    if action in {"0", "MENU"}:
        _set_wa(phone, "kids_hub", kids_close_step=None)
        return _kids_hub(language)

    def _affirm() -> str:
        affirmation = kids_affirmation(
            title, language=language, age_band=age_band, max_chars=400
        )
        _set_wa(phone, "kids_hub", kids_close_step=None)
        return f"{affirmation}\n\n{_kids_hub(language)}"

    if step == "after_prayer":
        if action == "1":
            return _affirm()
        return f"1. {t(language, 'kids_affirm')}\n0. {t(language, 'home')}"
    if action == "2":
        return _affirm()
    if action == "1":
        prayer = kids_prayer(title, language=language, age_band=age_band, max_chars=400)
        _set_wa(phone, "kids_close", kids_close_step="after_prayer")
        return (
            f"{prayer}\n\n"
            f"1. {t(language, 'kids_affirm')}\n"
            f"0. {t(language, 'home')}"
        )
    return _offer_kids_close_wa(phone, session, "quiz_finished")


def _handle_kids_plans(phone: str, session: dict[str, Any], action: str) -> WaOut:
    language = _lang(session)
    if action in {"0", "MENU"}:
        _set_wa(phone, "kids_hub")
        return _kids_hub(language)
    topics = list_plan_topics()
    try:
        choice = int(action)
    except ValueError:
        return _handle_kids_hub(phone, session, "3")
    if choice < 1 or choice > len(topics):
        return _handle_kids_hub(phone, session, "3")
    plan_id, _label = topics[choice - 1]
    session = _set_wa(
        phone, "kids_plan_day", kids_plan_id=plan_id, kids_plan_day=1
    )
    return _serve_kids_plan_day_wa(phone, session)


def _serve_kids_plan_day_wa(phone: str, session: dict[str, Any]) -> WaOut:
    language = _lang(session)
    age_band = str(session.get("age_band") or "6_9")
    plan_id = str(session.get("kids_plan_id") or "kindness")
    day = int(session.get("kids_plan_day") or 1)
    try:
        plan = get_kids_plan(plan_id)
        day_row = get_kids_plan_day(plan_id, day)
        total = kids_plan_day_count(plan_id)
    except ValueError:
        _set_wa(phone, "kids_plans")
        return _handle_kids_hub(phone, session, "3")
    body_text = translate_line(
        day_row["text"], language=language, age_band=age_band, max_chars=400
    )
    header = f"{plan['title']} D{day}/{total}: {day_row['title']}"
    next_label = (
        t(language, "kids_plan_next")
        if day < total
        else t(language, "kids_plan_done")
    )
    body = (
        f"{header}\n{body_text}\n\n"
        f"1. {next_label}\n"
        f"0. {t(language, 'home')}"
    )
    # Seasonal visuals when the plan matches a story illustration.
    visual_map = {
        "christmas": "christmas_birth",
        "easter": "easter_risen",
        "miracles": "calms_storm",
        "kindness": "samaritan",
        "fruit": "loaves",
    }
    image = story_image_url(visual_map.get(plan_id, ""))
    _set_wa(phone, "kids_plan_day")
    if image:
        return _out(_image(image, caption=header), body)
    return body


def _handle_kids_plan_day(
    phone: str, session: dict[str, Any], action: str
) -> WaOut:
    language = _lang(session)
    if action in {"0", "MENU"}:
        _set_wa(phone, "kids_hub")
        return _kids_hub(language)
    plan_id = str(session.get("kids_plan_id") or "kindness")
    day = int(session.get("kids_plan_day") or 1)
    if action == "1":
        try:
            total = kids_plan_day_count(plan_id)
        except ValueError:
            _set_wa(phone, "kids_hub")
            return _kids_hub(language)
        if day < total:
            session = _set_wa(phone, "kids_plan_day", kids_plan_day=day + 1)
            return _serve_kids_plan_day_wa(phone, session)
        _set_wa(phone, "kids_hub")
        return (
            f"{t(language, 'kids_plan_finished', title=topic_label(plan_id))}\n\n"
            f"{_kids_hub(language)}"
        )
    return _serve_kids_plan_day_wa(phone, session)


def _build_reply(phone: str, text: str) -> WaOut:
    """Map inbound WhatsApp text using a small session flow state."""

    session = get_user_session(phone)
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        if session.get("language_set"):
            return _menu(_lang(session))
        return _handle_lang_picker(phone, session, "")

    if not session.get("language_set"):
        # Digit → language picker. Anything else (hi/hiii/…) opens English menu
        # so the first WhatsApp ping is never a silent dead-end.
        if cleaned.isdigit():
            _set_wa(phone, "lang")
            return _handle_lang_picker(phone, get_user_session(phone), cleaned)
        _set_wa(
            phone,
            "main",
            language="en",
            language_set=True,
            bible_id=None,
            sms_daily=True,
        )
        return (
            "Karibu! Welcome to Scripture Without Screens.\n"
            f"{_menu('en')}"
        )

    flow = str(session.get("wa_flow") or "main")
    action = cleaned

    if flow == "votd":
        return _handle_votd(phone, session, action)
    if flow == "bible_root":
        return _handle_bible_root(phone, session, action)
    if flow == "bible_books":
        return _handle_bible_books(phone, session, action)
    if flow == "bible_chapter_pick":
        return _handle_bible_chapter_pick(phone, session, action)
    if flow == "bible_read":
        return _handle_bible_read(phone, session, action)
    if flow == "version":
        return _handle_version(phone, session, action)
    if flow == "lang":
        return _handle_lang_picker(phone, session, action)
    if flow == "kids_age":
        return _handle_kids_age(phone, session, action)
    if flow == "kids_hub":
        return _handle_kids_hub(phone, session, action)
    if flow == "kids_votd":
        return _handle_kids_votd(phone, session, action)
    if flow == "kids_testament":
        return _handle_kids_testament(phone, session, action)
    if flow == "kids_stories":
        return _handle_kids_stories(phone, session, action)
    if flow == "kids_got_it":
        return _handle_kids_got_it(phone, session, action)
    if flow == "kids_quiz":
        return _handle_kids_quiz(phone, session, action)
    if flow == "kids_close":
        return _handle_kids_close(phone, session, action)
    if flow == "kids_plans":
        return _handle_kids_plans(phone, session, action)
    if flow == "kids_plan_day":
        return _handle_kids_plan_day(phone, session, action)
    return _handle_main(phone, session, action)


def _as_messages(reply: WaOut) -> list[dict[str, Any]]:
    """Normalize a string or message-part list for sending."""

    if isinstance(reply, str):
        return _text(reply)
    return reply


@router.get("/whatsapp/webhook")
def verify_whatsapp_webhook(
    hub_mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    hub_verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    hub_challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> Response:
    """Meta webhook verification handshake."""

    if hub_mode == "subscribe" and hub_verify_token == WHATSAPP_VERIFY_TOKEN:
        logger.info(
            "WhatsApp webhook verified (WABA id set: %s)",
            bool(WHATSAPP_BUSINESS_ACCOUNT_ID),
        )
        return PlainTextResponse(hub_challenge or "", status_code=200)
    raise HTTPException(status_code=403, detail="Webhook verification failed.")


@router.post("/whatsapp/webhook")
async def receive_whatsapp_webhook(
    request: Request,
    x_hub_signature_256: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    """Handle inbound WhatsApp messages from Meta Cloud API."""

    raw = await request.body()
    if not verify_webhook_signature(raw, x_hub_signature_256):
        logger.warning("WhatsApp webhook rejected: bad X-Hub-Signature-256")
        raise HTTPException(status_code=403, detail="Invalid signature.")

    try:
        payload: dict[str, Any] = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON.") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON object.")

    if not whatsapp_configured():
        logger.warning("WhatsApp inbound ignored: credentials not configured.")
        return {"status": "ignored"}

    inbound = extract_inbound_messages(payload)
    # Status callbacks arrive with no messages — that is normal.
    if not inbound:
        field = None
        try:
            field = payload["entry"][0]["changes"][0].get("field")
        except (KeyError, IndexError, TypeError, AttributeError):
            field = None
        logger.info(
            "WhatsApp webhook POST ok (no text messages; field=%s object=%s)",
            field,
            payload.get("object"),
        )
        return {"status": "ok"}

    for message in inbound:
        phone = _normalize_phone(message["from"])
        print(f"[whatsapp] inbound {phone}: {message['text'][:80]}", flush=True)
        try:
            reply = _build_reply(phone, message["text"])
            send_whatsapp_messages(phone, _as_messages(reply))
            print(f"[whatsapp] reply sent to {phone}", flush=True)
        except (WhatsAppError, ValueError) as exc:
            print(f"[whatsapp] SEND FAILED {phone}: {exc}", flush=True)
            logger.warning("WhatsApp send failed for %s: %s", phone, exc)
        except Exception as exc:  # noqa: BLE001 - never fail the webhook ACK
            print(f"[whatsapp] HANDLER ERROR {phone}: {exc}", flush=True)
            logger.exception("WhatsApp handler error for %s", phone)
            try:
                send_whatsapp_text(
                    phone,
                    "Something went wrong loading Scripture. Reply hi to try again.",
                )
            except Exception:
                pass

    return {"status": "ok"}


@router.get("/whatsapp/status")
def whatsapp_status() -> dict[str, Any]:
    """Lightweight config check (no secrets exposed)."""

    return {
        "configured": whatsapp_configured(),
        "phone_number_id_set": bool(WHATSAPP_PHONE_NUMBER_ID),
        "business_account_id_set": bool(WHATSAPP_BUSINESS_ACCOUNT_ID),
        "verify_token_set": bool(WHATSAPP_VERIFY_TOKEN),
        "webhook_path": "/whatsapp/webhook",
    }
