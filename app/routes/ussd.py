"""Africa's Talking USSD webhook routes with Redis-backed Kids Corner."""

from typing import Annotated, Any

from fastapi import APIRouter, Form
from fastapi.responses import PlainTextResponse

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
    section_count,
    topic_label,
)
from app.services.reading_plan import (
    get_plan,
    get_plan_reference,
    list_categories,
    list_plans_in_category,
    next_plan_day,
    plan_day_count,
    plan_label,
    plan_overview_lines,
)
from app.services.usfm import book_title, chapter_passage_id, parse_usfm
from app.services.youversion_client import (
    SUPPORTED_LANGUAGES,
    YouVersionError,
    YouVersionNotFoundError,
    cached_default_bible_id,
    get_book_chapter_count,
    get_passage,
    get_passage_detail,
    get_verse_of_the_day_detail,
    list_bibles,
    list_books,
    prefer_bible_id,
    warm_bibles_for_language,
)
from app.utils.formatters import format_for_ussd, ussd_page
from app.utils.i18n import (
    LANGUAGE_NATIVE_LABELS,
    category_name,
    main_menu,
    nav_footer,
    t,
)
from app.utils.session_store import get_user_session, update_user_session


router = APIRouter(tags=["ussd"])

BOOKS_PER_PAGE = 5
CHAPTERS_PER_PAGE = 8


def _lang(session: dict[str, Any] | None = None, **_ignored: Any) -> str:
    """Resolve UI language from a session document."""

    if session is None:
        return "en"
    return str(session.get("language") or "en")


def _parse_selections(text: str) -> list[str]:
    """Split Africa's Talking cumulative menu text into user selections."""

    return [selection.strip() for selection in text.split("*") if selection.strip()]


def _last_action(selections: list[str]) -> str:
    """Return the most recent USSD keypress."""

    return selections[-1] if selections else ""


def _ussd_response(status: str, message: str) -> PlainTextResponse:
    """Build a plain-text response using Africa's Talking control prefixes."""

    return PlainTextResponse(f"{status} {message}")


def _set_flow(phone_number: str, flow: str, **fields: Any) -> dict[str, Any]:
    """Persist USSD flow state and optional session fields."""

    return update_user_session(phone_number, ussd_flow=flow, **fields)


def _language_menu(
    welcome: bool = False, language: str | None = None
) -> str:
    """Build the language picker, optionally as a first-run welcome."""

    # Welcome stays bilingual-friendly; later picks use the current UI language.
    title = (
        t("en", "welcome_title")
        if welcome
        else t(language, "choose_language")
    )
    lines = [title]
    for index, (code, _label) in enumerate(SUPPORTED_LANGUAGES, start=1):
        native = LANGUAGE_NATIVE_LABELS.get(code, _label)
        lines.append(f"{index}. {native}")
    if not welcome:
        lines.append(f"0. {t(language, 'home')}")
    return "\n".join(lines)


def _version_menu(bibles: list[dict[str, Any]], language: str) -> str:
    """Build the Change Bible Version USSD submenu."""

    lines = [t(language, "choose_version")]
    for index, bible in enumerate(bibles, start=1):
        lines.append(f"{index}. {bible['abbreviation']}")
    lines.append(f"9. {t(language, 'cancel')}")
    lines.append(f"0. {t(language, 'home')}")
    return "\n".join(lines)


def _cancel_version_change(phone_number: str, session: dict[str, Any]) -> PlainTextResponse:
    """Abort Bible version picking and restore the previous version."""

    previous = session.get("version_previous_bible_id")
    language = _lang(session)
    _set_flow(
        phone_number,
        "main",
        bible_id=previous,
        version_previous_bible_id=None,
    )
    return _ussd_response(
        "CON",
        f"{t(language, 'version_cancelled')}\n{main_menu(language)}",
    )


def _reading_plan_root_menu(session: dict[str, Any]) -> str:
    """Continue current plan or start a new filtered plan."""

    language = _lang(session)
    plan_id = str(session.get("plan_id") or "hope-kenya")
    day = int(session.get("plan_day") or 1)
    label = plan_label(plan_id)
    return "\n".join(
        [
            t(language, "plan_title"),
            t(language, "plan_now", label=label, day=day),
            f"1. {t(language, 'plan_continue')}",
            f"2. {t(language, 'plan_new')}",
            nav_footer(language),
        ]
    )


def _plan_category_menu(language: str) -> str:
    """Topic filter menu (YouVersion-style categories)."""

    lines = [t(language, "plan_topic")]
    for index, (code, _label) in enumerate(list_categories(), start=1):
        lines.append(f"{index}. {category_name(language, code)}")
    lines.append(nav_footer(language))
    return "\n".join(lines)


def _plans_in_category_menu(category_id: str, language: str) -> str:
    """List plans inside one topic category."""

    plans = list_plans_in_category(category_id)
    cat = category_name(language, category_id)
    lines = [t(language, "plans_in_cat", category=cat)]
    if not plans:
        lines.append(t(language, "none_yet"))
    for index, plan in enumerate(plans, start=1):
        days = len(plan["days"])
        lines.append(
            f"{index}. {t(language, 'plan_days', title=plan['title'], days=days)}"
        )
    lines.append(nav_footer(language))
    return "\n".join(lines)


def _plan_preview_screen(session: dict[str, Any]) -> str:
    """Explain a plan with about text, refs, and a live sample verse."""

    plan_id = str(session.get("plan_preview_id") or session.get("plan_id") or "")
    language = _lang(session)
    bible_id = session.get("bible_id")
    lines = plan_overview_lines(plan_id, max_days_listed=3)
    about = lines[1] if len(lines) > 1 else ""
    # Localize the about blurb when the subscriber is not on English.
    if language != "en" and about:
        lines[1] = translate_line(about, language=language, age_band="10_12")
    try:
        day_one_ref = get_plan_reference(plan_id, 1)
        sample = get_passage(day_one_ref, language=language, bible_id=bible_id)
        lines.append(f"D1 {day_one_ref}:")
        lines.append(format_for_ussd(sample)[:90])
    except (ValueError, YouVersionError):
        lines.append(t(language, "plan_d1_fail"))
    lines.append(f"1. {t(language, 'start_plan')}")
    lines.append(f"2. {t(language, 'back_plans')}")
    lines.append(nav_footer(language))
    return "\n".join(lines)


def _age_menu(language: str) -> str:
    """Build the Kids Corner age-band menu."""

    lines = [t(language, "kids_age")]
    for index, (code, _label) in enumerate(AGE_BANDS, start=1):
        lines.append(f"{index}. {t(language, f'age_{code}')}")
    lines.append(nav_footer(language))
    return "\n".join(lines)


def _kids_hub_menu(language: str) -> str:
    """Kids hub: morning VOTD, stories, and topic plans."""

    return "\n".join(
        [
            t(language, "kids_hub"),
            f"1. {t(language, 'kids_menu_votd')}",
            f"2. {t(language, 'kids_menu_stories')}",
            f"3. {t(language, 'kids_menu_plans')}",
            f"0. {t(language, 'home')}",
        ]
    )


def _kids_close_menu(language: str, intro: str) -> str:
    """After a story quiz: prayer or affirmation."""

    return "\n".join(
        [
            intro,
            f"1. {t(language, 'kids_pray')}",
            f"2. {t(language, 'kids_affirm')}",
            f"0. {t(language, 'home')}",
        ]
    )


def _kids_testament_menu(language: str) -> str:
    """Old / New Testament picker for kids stories."""

    return "\n".join(
        [
            t(language, "kids_pick_testament"),
            f"1. {t(language, 'read_ot')}",
            f"2. {t(language, 'read_nt')}",
            f"0. {t(language, 'home')}",
        ]
    )


def _story_menu(session: dict[str, Any]) -> str:
    """Build the kids story picker for age + testament."""

    language = _lang(session)
    age_band = str(session.get("age_band") or "6_9")
    testament = str(session.get("kids_testament") or "old")
    stories = list_stories_for_age(age_band, testament=testament)
    heading = t(
        language,
        "kids_stories_ot" if testament == "old" else "kids_stories_nt",
    )
    lines = [heading]
    current_id = session.get("kids_story_id")
    offset = 1
    if current_id:
        try:
            story = get_story(str(current_id))
            if story.get("testament") == testament:
                lines.append(
                    f"1. {t(language, 'kids_continue', title=story['title'])}"
                )
                offset = 2
            else:
                current_id = None
        except ValueError:
            current_id = None
    for index, story in enumerate(stories, start=offset):
        lines.append(f"{index}. {story['title']}")
    if not stories and offset == 1:
        lines.append(t(language, "none_yet"))
    lines.append(nav_footer(language))
    return "\n".join(lines)


def _kids_plans_menu(language: str) -> str:
    """Topic list for kids reading plans."""

    lines = [t(language, "kids_plans_title")]
    for index, (code, _label) in enumerate(list_plan_topics(), start=1):
        key = f"kids_plan_{code}"
        lines.append(f"{index}. {t(language, key)}")
    lines.append(nav_footer(language))
    return "\n".join(lines)


def _got_it_menu(section_text: str, language: str) -> str:
    """Show a story section and ask if the child understands."""

    body = format_for_ussd(section_text)
    # Leave room for the choice lines inside a CON screen (~182 is ok on many
    # networks; still keep choices short).
    return (
        f"{body}\n"
        f"1. {t(language, 'got_it')}\n"
        f"2. {t(language, 'explain_simpler')}\n"
        f"{nav_footer(language)}"
    )


def _show_main(phone_number: str) -> PlainTextResponse:
    """Return the main menu and mark flow as main."""

    session = _set_flow(phone_number, "main")
    return _ussd_response("CON", main_menu(_lang(session)))


def _apply_language(
    phone_number: str, choice: str, *, then_main: bool
) -> PlainTextResponse:
    """Apply a numbered language choice."""

    try:
        index = int(choice)
    except ValueError:
        return _ussd_response("END", t("en", "invalid_language"))
    if index < 1 or index > len(SUPPORTED_LANGUAGES):
        return _ussd_response("END", t("en", "invalid_language"))
    language_code, _english_label = SUPPORTED_LANGUAGES[index - 1]
    language_label = LANGUAGE_NATIVE_LABELS.get(language_code, _english_label)
    # Never block the USSD reply on YouVersion. Reuse a cached default Bible
    # when we have one; otherwise clear and warm the list in the background.
    default_bible = cached_default_bible_id(language_code)
    _set_flow(
        phone_number,
        "main",
        language=language_code,
        language_set=True,
        bible_id=default_bible,
    )
    warm_bibles_for_language(language_code)
    if then_main:
        return _ussd_response(
            "CON",
            f"{t(language_code, 'language_set', label=language_label)}\n"
            f"{main_menu(language_code)}",
        )
    return _ussd_response(
        "END",
        t(language_code, "language_set_end", label=language_label),
    )


def _votd_action_footer(language: str) -> str:
    """Menu keys under Verse of the Day / explain / pray screens."""

    return "\n".join(
        [
            f"1. {t(language, 'votd_explain')}",
            f"2. {t(language, 'votd_pray')}",
            f"3. {t(language, 'votd_chapter')}",
            nav_footer(language),
        ]
    )


def _render_scroll(
    phone_number: str,
    *,
    flow: str,
    body: str,
    footer: str,
    language: str,
    page: int = 0,
    reset_text: bool = True,
    **session_fields: Any,
) -> PlainTextResponse:
    """Show one page of long scripture/reflection with optional ``9. More``."""

    more_line = f"9. {t(language, 'more_text')}"
    if reset_text:
        session_fields["scroll_text"] = body
        session_fields["scroll_page"] = page
    else:
        session_fields.setdefault("scroll_page", page)
    screen, _total, _has_more = ussd_page(body, footer, more_line, page=page)
    _set_flow(phone_number, flow, **session_fields)
    return _ussd_response("CON", screen)


def _advance_scroll(
    phone_number: str,
    session: dict[str, Any],
    *,
    flow: str,
    footer: str,
    language: str,
) -> PlainTextResponse | None:
    """Handle ``9. More`` when scroll text is stored; else return ``None``."""

    body = session.get("scroll_text")
    if not isinstance(body, str) or not body.strip():
        return None
    page = int(session.get("scroll_page") or 0) + 1
    return _render_scroll(
        phone_number,
        flow=flow,
        body=body,
        footer=footer,
        language=language,
        page=page,
        reset_text=False,
        scroll_text=body,
        scroll_page=page,
    )


def _open_verse_of_the_day(
    phone_number: str, session: dict[str, Any], *, page: int = 0
) -> PlainTextResponse:
    """Load YouVersion's VOTD with citation into a continuing menu."""

    language = _lang(session)
    try:
        detail = get_verse_of_the_day_detail(
            language=language,
            bible_id=session.get("bible_id"),
        )
    except YouVersionError:
        return _ussd_response("END", t(language, "votd_unavailable"))
    body = f"{detail['reference']}\n{detail['text']}"
    return _render_scroll(
        phone_number,
        flow="votd",
        body=body,
        footer=_votd_action_footer(language),
        language=language,
        page=page,
        votd_passage_id=detail["passage_id"],
    )


def _bible_root_menu(session: dict[str, Any]) -> str:
    """Read My Bible entry: continue or pick testament."""

    language = _lang(session)
    lines = [t(language, "read_bible_title")]
    book = session.get("read_book")
    chapter = session.get("read_chapter")
    if book and chapter:
        place = f"{book_title(str(book))} {chapter}"
        lines.append(t(language, "read_last", place=place))
        lines.append(f"1. {t(language, 'read_continue')}")
        lines.append(f"2. {t(language, 'read_ot')}")
        lines.append(f"3. {t(language, 'read_nt')}")
    else:
        lines.append(f"1. {t(language, 'read_ot')}")
        lines.append(f"2. {t(language, 'read_nt')}")
    lines.append(nav_footer(language))
    return "\n".join(lines)


def _books_menu(session: dict[str, Any]) -> str:
    """Paginated book list for the selected testament."""

    language = _lang(session)
    testament = str(session.get("read_testament") or "old")
    page = int(session.get("read_book_page") or 0)
    try:
        books = list_books(
            language, bible_id=session.get("bible_id"), testament=testament
        )
    except YouVersionError:
        return t(language, "books_fail") + "\n" + nav_footer(language)

    start = page * BOOKS_PER_PAGE
    chunk = books[start : start + BOOKS_PER_PAGE]
    heading = t(language, "books_ot" if testament == "old" else "books_nt")
    lines = [heading]
    for index, book in enumerate(chunk, start=1):
        lines.append(f"{index}. {book['title']}")
    if start + BOOKS_PER_PAGE < len(books):
        lines.append(f"9. {t(language, 'more_books')}")
    if page > 0:
        lines.append(f"7. {t(language, 'previous')}")
    lines.append(nav_footer(language))
    return "\n".join(lines)


def _chapters_menu(session: dict[str, Any]) -> str:
    """Paginated chapter picker for the selected book."""

    book = str(session.get("read_book") or "GEN")
    page = int(session.get("read_chapter_page") or 0)
    language = _lang(session)
    try:
        total = get_book_chapter_count(
            book, language=language, bible_id=session.get("bible_id")
        )
    except YouVersionError:
        return t(language, "chapters_fail") + "\n" + nav_footer(language)

    start = page * CHAPTERS_PER_PAGE + 1
    end = min(start + CHAPTERS_PER_PAGE - 1, total)
    lines = [t(language, "chapters_title", book=book_title(book))]
    for chapter in range(start, end + 1):
        # Map menu digits 1..n onto absolute chapter numbers.
        lines.append(
            f"{chapter - start + 1}. {t(language, 'chapter_n', n=chapter)}"
        )
    if end < total:
        lines.append(f"9. {t(language, 'more_chapters')}")
    if page > 0:
        lines.append(f"7. {t(language, 'previous')}")
    lines.append(nav_footer(language))
    return "\n".join(lines)


def _bible_read_footer(language: str) -> str:
    """Actions under a chapter page."""

    return "\n".join(
        [
            f"1. {t(language, 'next_chapter')}",
            f"2. {t(language, 'pray_option')}",
            f"0. {t(language, 'home')}",
        ]
    )


def _show_bible_chapter(
    phone_number: str,
    session: dict[str, Any],
    *,
    page: int = 0,
    reuse_scroll: bool = False,
) -> PlainTextResponse:
    """Display a chapter in USSD pages (press 9 for More)."""

    book = str(session.get("read_book") or "GEN")
    chapter = int(session.get("read_chapter") or 1)
    language = _lang(session)
    footer = _bible_read_footer(language)
    if reuse_scroll and isinstance(session.get("scroll_text"), str):
        return _render_scroll(
            phone_number,
            flow="bible_read",
            body=str(session["scroll_text"]),
            footer=footer,
            language=language,
            page=page,
            reset_text=False,
            scroll_text=session["scroll_text"],
            scroll_page=page,
            read_verse=1,
        )

    passage_id = chapter_passage_id(book, chapter)
    try:
        detail = get_passage_detail(
            passage_id, language=language, bible_id=session.get("bible_id")
        )
    except YouVersionError:
        return _ussd_response("END", t(language, "chapter_load_fail"))
    body = f"{detail['reference']}\n{detail['text']}"
    return _render_scroll(
        phone_number,
        flow="bible_read",
        body=body,
        footer=footer,
        language=language,
        page=page,
        read_verse=1,
    )


def _serve_plan_day(
    phone_number: str,
    session: dict[str, Any],
    *,
    page: int = 0,
    reuse_scroll: bool = False,
) -> PlainTextResponse:
    """Serve today's plan passage in pages, then offer a short prayer."""

    plan_id = str(session.get("plan_id") or "hope-kenya")
    day_number = int(session.get("plan_day") or 1)
    total = plan_day_count(plan_id)
    language = _lang(session)
    footer = "\n".join(
        [
            f"1. {t(language, 'pray_option')}",
            f"0. {t(language, 'home')}",
        ]
    )
    if reuse_scroll and isinstance(session.get("scroll_text"), str):
        return _render_scroll(
            phone_number,
            flow="plan_close",
            body=str(session["scroll_text"]),
            footer=footer,
            language=language,
            page=page,
            reset_text=False,
            scroll_text=session["scroll_text"],
            scroll_page=page,
        )

    try:
        reference = get_plan_reference(plan_id, day_number)
        detail = get_passage_detail(
            reference,
            language=language,
            bible_id=session.get("bible_id"),
        )
    except (ValueError, YouVersionError):
        return _ussd_response("END", t(language, "plan_fail"))
    update_user_session(
        phone_number,
        plan_day=next_plan_day(plan_id, day_number),
        plan_close_ref=detail["reference"],
        plan_close_text=detail["text"],
    )
    label = plan_label(plan_id)
    body = (
        f"{label} D{day_number}/{total} {detail['reference']}: {detail['text']}"
    )
    return _render_scroll(
        phone_number,
        flow="plan_close",
        body=body,
        footer=footer,
        language=language,
        page=page,
    )


def _enter_reading_plans(
    phone_number: str, session: dict[str, Any]
) -> PlainTextResponse:
    """Open the reading-plan root: continue or start new."""

    _set_flow(phone_number, "plan")
    return _ussd_response("CON", _reading_plan_root_menu(session))


def _present_kids_section(
    phone_number: str, session: dict[str, Any]
) -> PlainTextResponse:
    """Load the current kids section (translated if needed) and ask Got it."""

    story_id = str(session.get("kids_story_id") or "")
    section_index = int(session.get("kids_section") or 0)
    age_band = str(session.get("age_band") or "6_9")
    language = str(session.get("language") or "en")
    try:
        english = get_section(story_id, section_index)
    except ValueError:
        _set_flow(phone_number, "kids_stories")
        return _ussd_response("CON", _story_menu(session))

    display = translate_line(english, language=language, age_band=age_band)
    _set_flow(phone_number, "kids_got_it")
    return _ussd_response("CON", _got_it_menu(display, language))


def _start_quiz(phone_number: str, session: dict[str, Any]) -> PlainTextResponse:
    """Begin the quiz for the current story."""

    _set_flow(
        phone_number,
        "kids_quiz",
        kids_quiz_index=0,
        kids_quiz_retries=0,
    )
    session = get_user_session(phone_number)
    return _quiz_prompt(session)


def _quiz_text(session: dict[str, Any]) -> str:
    """Build quiz question text without wrapping in an HTTP response."""

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
    lines.append(nav_footer(language))
    return "\n".join(lines)


def _quiz_prompt(session: dict[str, Any]) -> PlainTextResponse:
    """Render the current quiz question."""

    story_id = str(session.get("kids_story_id") or "")
    age_band = str(session.get("age_band") or "6_9")
    index = int(session.get("kids_quiz_index") or 0)
    questions = get_quiz_questions(story_id, age_band)
    text = _quiz_text(session)
    if index >= len(questions):
        return _ussd_response("END", format_for_ussd(text))
    return _ussd_response("CON", text)


def _handle_nav_or_continue(
    phone_number: str, action: str, session: dict[str, Any]
) -> PlainTextResponse | None:
    """Handle global 8/5 language and 0 home keys when present.

    Returns:
        A response if navigation consumed the key, otherwise ``None``.
    """

    if action == "0":
        return _show_main(phone_number)
    if action in {"8", "5"} and session.get("ussd_flow") != "main":
        # Nested screens use 8; main uses 5 — both open language picker.
        if action == "5" and session.get("ussd_flow") == "main":
            return None
        _set_flow(phone_number, "lang")
        return _ussd_response(
            "CON", _language_menu(welcome=False, language=_lang(session))
        )
    return None


def _enter_kids(phone_number: str, session: dict[str, Any]) -> PlainTextResponse:
    """Enter Kids Corner at age gate or Stories / Plans hub."""

    language = _lang(session)
    if not session.get("age_band"):
        _set_flow(phone_number, "kids_age")
        return _ussd_response("CON", _age_menu(language))
    _set_flow(phone_number, "kids_hub")
    return _ussd_response("CON", _kids_hub_menu(language))


def _kids_bible_id(session: dict[str, Any], language: str) -> int | None:
    """Prefer NIV for kids English; else session / first licensed version."""

    fallback = session.get("bible_id")
    fallback_id = fallback if isinstance(fallback, int) else None
    if language in {"en", "eng"}:
        return prefer_bible_id(
            language, abbreviations=("NIV11", "NIV", "NIrV"), fallback=fallback_id
        )
    return prefer_bible_id(
        language, abbreviations=("NIV", "NIrV", "BSB"), fallback=fallback_id
    )


def _open_kids_votd(
    phone_number: str, session: dict[str, Any]
) -> PlainTextResponse:
    """Kids morning: real NIV verse + short meaning/example, then pray/affirm."""

    language = _lang(session)
    age_band = str(session.get("age_band") or "6_9")
    try:
        detail = get_verse_of_the_day_detail(
            language=language, bible_id=_kids_bible_id(session, language)
        )
    except YouVersionError:
        return _ussd_response("END", t(language, "votd_unavailable"))
    explanation = explain_votd_for_kid(
        detail["reference"],
        detail["text"],
        language=language,
        age_band=age_band,
        max_chars=160,
    )
    _set_flow(
        phone_number,
        "kids_votd",
        votd_passage_id=detail["passage_id"],
        kids_votd_ref=detail["reference"],
        kids_votd_text=detail["text"],
        kids_close_step="choose",
    )
    body = format_for_ussd(
        f"{detail['reference']} (NIV)\n{detail['text']}\n\n{explanation}"
    )
    return _ussd_response(
        "CON",
        f"{body}\n"
        f"1. {t(language, 'kids_pray')}\n"
        f"2. {t(language, 'kids_affirm')}\n"
        f"0. {t(language, 'home')}",
    )


def _offer_kids_story_close(
    phone_number: str, session: dict[str, Any], intro_key: str, **intro_kwargs: Any
) -> PlainTextResponse:
    """After quiz: lead into prayer or affirmation for the story."""

    language = _lang(session)
    intro = t(language, intro_key, **intro_kwargs)
    _set_flow(
        phone_number,
        "kids_close",
        kids_section=0,
        kids_quiz_index=0,
        kids_quiz_retries=0,
        kids_close_step="choose",
    )
    return _ussd_response(
        "CON", _kids_close_menu(language, format_for_ussd(intro))
    )


def _serve_kids_plan_day(
    phone_number: str, session: dict[str, Any]
) -> PlainTextResponse:
    """Show one kids plan day with next-day / Home controls."""

    language = _lang(session)
    plan_id = str(session.get("kids_plan_id") or "kindness")
    day = int(session.get("kids_plan_day") or 1)
    age_band = str(session.get("age_band") or "6_9")
    try:
        plan = get_kids_plan(plan_id)
        day_row = get_kids_plan_day(plan_id, day)
        total = kids_plan_day_count(plan_id)
    except ValueError:
        _set_flow(phone_number, "kids_plans")
        return _ussd_response("CON", _kids_plans_menu(language))

    body = translate_line(
        day_row["text"], language=language, age_band=age_band
    )
    header = f"{plan['title']} D{day}/{total}: {day_row['title']}"
    screen = format_for_ussd(f"{header}\n{body}")
    _set_flow(phone_number, "kids_plan_day")
    lines = [screen]
    if day < total:
        lines.append(f"1. {t(language, 'kids_plan_next')}")
    else:
        lines.append(f"1. {t(language, 'kids_plan_done')}")
    lines.append(f"0. {t(language, 'home')}")
    return _ussd_response("CON", "\n".join(lines))


def _pick_story_from_menu(
    phone_number: str, session: dict[str, Any], action: str
) -> PlainTextResponse:
    """Map a story-menu digit to continue or a listed story."""

    age_band = str(session.get("age_band") or "6_9")
    testament = str(session.get("kids_testament") or "old")
    stories = list_stories_for_age(age_band, testament=testament)
    current_id = session.get("kids_story_id")
    resume_ok = False
    if current_id:
        try:
            resume_ok = get_story(str(current_id)).get("testament") == testament
        except ValueError:
            resume_ok = False
    try:
        choice = int(action)
    except ValueError:
        return _ussd_response("CON", _story_menu(session))

    if resume_ok:
        if choice == 1:
            return _present_kids_section(phone_number, session)
        story_index = choice - 2
    else:
        story_index = choice - 1

    if story_index < 0 or story_index >= len(stories):
        return _ussd_response("CON", _story_menu(session))

    story = stories[story_index]
    session = _set_flow(
        phone_number,
        "kids_got_it",
        kids_story_id=story["id"],
        kids_section=0,
        kids_quiz_index=0,
        kids_quiz_retries=0,
    )
    return _present_kids_section(phone_number, session)


def _handle_flow(
    phone_number: str, session: dict[str, Any], action: str
) -> PlainTextResponse:
    """Dispatch one keypress based on Redis ``ussd_flow``."""

    flow = str(session.get("ussd_flow") or "main")

    if flow == "lang":
        if action == "0" and session.get("language_set"):
            return _show_main(phone_number)
        return _apply_language(phone_number, action, then_main=True)

    nav = _handle_nav_or_continue(phone_number, action, session)
    if nav is not None and flow != "main":
        return nav

    if flow == "main":
        language = _lang(session)
        if action == "0":
            return _show_main(phone_number)
        if action == "1":
            return _open_verse_of_the_day(phone_number, session)
        if action == "2":
            _set_flow(phone_number, "bible_root")
            return _ussd_response("CON", _bible_root_menu(session))
        if action == "3":
            return _enter_reading_plans(phone_number, session)
        if action == "4":
            return _enter_kids(phone_number, session)
        if action == "5":
            try:
                bibles = list_bibles(language, limit=5)
            except YouVersionNotFoundError:
                return _ussd_response("END", t(language, "no_bible_lang"))
            except YouVersionError:
                return _ussd_response("END", t(language, "versions_fail"))
            _set_flow(
                phone_number,
                "version",
                version_previous_bible_id=session.get("bible_id"),
            )
            return _ussd_response("CON", _version_menu(bibles, language))
        if action == "6":
            _set_flow(phone_number, "lang")
            return _ussd_response(
                "CON", _language_menu(welcome=False, language=language)
            )
        return _ussd_response("CON", main_menu(language))

    if flow == "votd":
        language = _lang(session)
        passage_id = str(session.get("votd_passage_id") or "")
        if not passage_id:
            return _open_verse_of_the_day(phone_number, session)
        if action == "9":
            advanced = _advance_scroll(
                phone_number,
                session,
                flow="votd",
                footer=_votd_action_footer(language),
                language=language,
            )
            if advanced is not None:
                return advanced
        try:
            detail = get_passage_detail(
                passage_id, language=language, bible_id=session.get("bible_id")
            )
        except YouVersionError:
            return _ussd_response("END", t(language, "verse_unavailable"))
        if action == "1":
            explanation = explain_scripture(
                detail["reference"],
                detail["text"],
                language=language,
                max_chars=600,
            )
            return _render_scroll(
                phone_number,
                flow="votd",
                body=explanation,
                footer=_votd_action_footer(language),
                language=language,
                page=0,
                votd_passage_id=passage_id,
            )
        if action == "2":
            prayer = write_prayer(
                detail["reference"],
                detail["text"],
                language=language,
                max_chars=600,
            )
            return _render_scroll(
                phone_number,
                flow="votd",
                body=prayer,
                footer=_votd_action_footer(language),
                language=language,
                page=0,
                votd_passage_id=passage_id,
            )
        if action == "3":
            book, chapter, _verse = parse_usfm(passage_id)
            if not book or not chapter:
                return _ussd_response("END", t(language, "chapter_unavailable"))
            session = _set_flow(
                phone_number,
                "bible_read",
                read_book=book,
                read_chapter=chapter,
                read_verse=1,
            )
            return _show_bible_chapter(phone_number, session)
        return _render_scroll(
            phone_number,
            flow="votd",
            body=f"{detail['reference']}\n{detail['text']}",
            footer=_votd_action_footer(language),
            language=language,
            page=0,
            votd_passage_id=passage_id,
        )

    if flow == "bible_root":
        has_resume = bool(session.get("read_book") and session.get("read_chapter"))
        if has_resume:
            if action == "1":
                return _show_bible_chapter(phone_number, session)
            if action == "2":
                _set_flow(
                    phone_number,
                    "bible_books",
                    read_testament="old",
                    read_book_page=0,
                )
                return _ussd_response(
                    "CON", _books_menu(get_user_session(phone_number))
                )
            if action == "3":
                _set_flow(
                    phone_number,
                    "bible_books",
                    read_testament="new",
                    read_book_page=0,
                )
                return _ussd_response(
                    "CON", _books_menu(get_user_session(phone_number))
                )
        else:
            if action == "1":
                _set_flow(
                    phone_number,
                    "bible_books",
                    read_testament="old",
                    read_book_page=0,
                )
                return _ussd_response(
                    "CON", _books_menu(get_user_session(phone_number))
                )
            if action == "2":
                _set_flow(
                    phone_number,
                    "bible_books",
                    read_testament="new",
                    read_book_page=0,
                )
                return _ussd_response(
                    "CON", _books_menu(get_user_session(phone_number))
                )
        return _ussd_response("CON", _bible_root_menu(session))

    if flow == "bible_books":
        if action == "9":
            page = int(session.get("read_book_page") or 0) + 1
            session = _set_flow(phone_number, "bible_books", read_book_page=page)
            return _ussd_response("CON", _books_menu(session))
        if action == "7":
            page = max(0, int(session.get("read_book_page") or 0) - 1)
            session = _set_flow(phone_number, "bible_books", read_book_page=page)
            return _ussd_response("CON", _books_menu(session))
        try:
            choice = int(action)
        except ValueError:
            return _ussd_response("CON", _books_menu(session))
        if choice < 1 or choice > BOOKS_PER_PAGE:
            return _ussd_response("CON", _books_menu(session))
        language = str(session.get("language") or "en")
        testament = str(session.get("read_testament") or "old")
        page = int(session.get("read_book_page") or 0)
        try:
            books = list_books(
                language, bible_id=session.get("bible_id"), testament=testament
            )
        except YouVersionError:
            return _ussd_response("END", t(_lang(session), "books_fail"))
        index = page * BOOKS_PER_PAGE + (choice - 1)
        if index < 0 or index >= len(books):
            return _ussd_response("CON", _books_menu(session))
        book = books[index]
        session = _set_flow(
            phone_number,
            "bible_chapters",
            read_book=book["id"],
            read_chapter_page=0,
        )
        return _ussd_response("CON", _chapters_menu(session))

    if flow == "bible_chapters":
        if action == "9":
            page = int(session.get("read_chapter_page") or 0) + 1
            session = _set_flow(
                phone_number, "bible_chapters", read_chapter_page=page
            )
            return _ussd_response("CON", _chapters_menu(session))
        if action == "7":
            page = max(0, int(session.get("read_chapter_page") or 0) - 1)
            session = _set_flow(
                phone_number, "bible_chapters", read_chapter_page=page
            )
            return _ussd_response("CON", _chapters_menu(session))
        try:
            choice = int(action)
        except ValueError:
            return _ussd_response("CON", _chapters_menu(session))
        if choice < 1 or choice > CHAPTERS_PER_PAGE:
            return _ussd_response("CON", _chapters_menu(session))
        page = int(session.get("read_chapter_page") or 0)
        chapter = page * CHAPTERS_PER_PAGE + choice
        book = str(session.get("read_book") or "GEN")
        language = str(session.get("language") or "en")
        try:
            total = get_book_chapter_count(
                book, language=language, bible_id=session.get("bible_id")
            )
        except YouVersionError:
            return _ussd_response("END", t(_lang(session), "chapters_fail"))
        if chapter < 1 or chapter > total:
            return _ussd_response("CON", _chapters_menu(session))
        session = _set_flow(
            phone_number,
            "bible_read",
            read_chapter=chapter,
            read_verse=1,
        )
        return _show_bible_chapter(phone_number, session)

    if flow == "bible_read":
        # Chapter reading: 9 = More text, 1 = next chapter, 2 = pray, 0 = Home.
        language = _lang(session)
        book = str(session.get("read_book") or "GEN")
        chapter = int(session.get("read_chapter") or 1)
        if action == "9":
            advanced = _advance_scroll(
                phone_number,
                session,
                flow="bible_read",
                footer=_bible_read_footer(language),
                language=language,
            )
            if advanced is not None:
                return advanced
            return _show_bible_chapter(
                phone_number, session, page=1, reuse_scroll=False
            )
        if action == "1":
            try:
                total_chapters = get_book_chapter_count(
                    book, language=language, bible_id=session.get("bible_id")
                )
            except YouVersionError:
                return _ussd_response("END", t(language, "chapter_load_fail"))
            if chapter < total_chapters:
                session = _set_flow(
                    phone_number,
                    "bible_read",
                    read_chapter=chapter + 1,
                    read_verse=1,
                    scroll_text=None,
                    scroll_page=0,
                )
                return _show_bible_chapter(phone_number, session)
            _set_flow(phone_number, "main")
            return _ussd_response(
                "CON",
                f"{t(language, 'book_done', book=book_title(book))}\n"
                f"{main_menu(language)}",
            )
        if action == "2":
            try:
                detail = get_passage_detail(
                    chapter_passage_id(book, chapter),
                    language=language,
                    bible_id=session.get("bible_id"),
                )
            except YouVersionError:
                return _ussd_response("END", t(language, "chapter_load_fail"))
            prayer = write_prayer(
                detail["reference"],
                detail["text"],
                language=language,
                max_chars=600,
            )
            footer = "\n".join(
                [
                    f"1. {t(language, 'next_chapter')}",
                    f"0. {t(language, 'home')}",
                ]
            )
            return _render_scroll(
                phone_number,
                flow="bible_read",
                body=prayer,
                footer=footer,
                language=language,
                page=0,
            )
        return _show_bible_chapter(phone_number, session)

    if flow == "plan":
        language = _lang(session)
        if action == "1":
            return _serve_plan_day(phone_number, session)
        if action == "2":
            _set_flow(phone_number, "plan_categories")
            return _ussd_response("CON", _plan_category_menu(language))
        return _ussd_response("CON", _reading_plan_root_menu(session))

    if flow == "plan_close":
        language = _lang(session)
        if action == "9":
            footer = "\n".join(
                [
                    f"1. {t(language, 'pray_option')}",
                    f"0. {t(language, 'home')}",
                ]
            )
            advanced = _advance_scroll(
                phone_number,
                session,
                flow="plan_close",
                footer=footer,
                language=language,
            )
            if advanced is not None:
                return advanced
        if action == "1":
            reference = str(session.get("plan_close_ref") or "")
            text = str(session.get("plan_close_text") or "")
            prayer = write_prayer(
                reference, text, language=language, max_chars=600
            )
            _set_flow(phone_number, "main")
            return _ussd_response(
                "END",
                format_for_ussd(prayer),
            )
        return _show_main(phone_number)

    if flow == "plan_categories":
        language = _lang(session)
        try:
            choice = int(action)
        except ValueError:
            return _ussd_response("CON", _plan_category_menu(language))
        categories = list_categories()
        if choice < 1 or choice > len(categories):
            return _ussd_response("CON", _plan_category_menu(language))
        category_id, _label = categories[choice - 1]
        _set_flow(phone_number, "plan_list", plan_category=category_id)
        return _ussd_response(
            "CON", _plans_in_category_menu(category_id, language)
        )

    if flow == "plan_list":
        language = _lang(session)
        category_id = str(session.get("plan_category") or "hope")
        plans = list_plans_in_category(category_id)
        try:
            choice = int(action)
        except ValueError:
            return _ussd_response(
                "CON", _plans_in_category_menu(category_id, language)
            )
        if choice < 1 or choice > len(plans):
            return _ussd_response(
                "CON", _plans_in_category_menu(category_id, language)
            )
        plan = plans[choice - 1]
        session = _set_flow(
            phone_number,
            "plan_preview",
            plan_preview_id=plan["id"],
        )
        return _ussd_response("CON", _plan_preview_screen(session))

    if flow == "plan_preview":
        language = _lang(session)
        if action == "2":
            category_id = str(session.get("plan_category") or "hope")
            _set_flow(phone_number, "plan_list")
            return _ussd_response(
                "CON", _plans_in_category_menu(category_id, language)
            )
        if action == "1":
            preview_id = str(
                session.get("plan_preview_id") or session.get("plan_id") or ""
            )
            try:
                get_plan(preview_id)
            except ValueError:
                _set_flow(phone_number, "plan_categories")
                return _ussd_response("CON", _plan_category_menu(language))
            session = _set_flow(
                phone_number,
                "plan",
                plan_id=preview_id,
                plan_day=1,
                plan_preview_id=None,
            )
            # Immediately serve day 1 so the farmer hears scripture right away.
            return _serve_plan_day(phone_number, session)
        return _ussd_response("CON", _plan_preview_screen(session))

    if flow == "version":
        language = _lang(session)
        if action in {"0", "9"}:
            return _cancel_version_change(phone_number, session)
        try:
            bibles = list_bibles(language, limit=5)
        except YouVersionError:
            return _ussd_response("END", t(language, "versions_fail"))
        try:
            choice = int(action)
        except ValueError:
            return _ussd_response("CON", _version_menu(bibles, language))
        if choice < 1 or choice > len(bibles):
            return _ussd_response("CON", _version_menu(bibles, language))
        selected = bibles[choice - 1]
        _set_flow(
            phone_number,
            "main",
            bible_id=selected["id"],
            version_previous_bible_id=None,
        )
        return _ussd_response(
            "CON",
            f"{t(language, 'bible_set', abbr=selected['abbreviation'])}\n"
            f"{main_menu(language)}",
        )

    if flow == "kids_age":
        language = _lang(session)
        try:
            choice = int(action)
        except ValueError:
            return _ussd_response("CON", _age_menu(language))
        if choice < 1 or choice > len(AGE_BANDS):
            return _ussd_response("CON", _age_menu(language))
        age_code, _label = AGE_BANDS[choice - 1]
        _set_flow(phone_number, "kids_hub", age_band=age_code)
        return _ussd_response("CON", _kids_hub_menu(language))

    if flow == "kids_hub":
        language = _lang(session)
        if action == "1":
            return _open_kids_votd(phone_number, session)
        if action == "2":
            _set_flow(phone_number, "kids_testament")
            return _ussd_response("CON", _kids_testament_menu(language))
        if action == "3":
            _set_flow(phone_number, "kids_plans")
            return _ussd_response("CON", _kids_plans_menu(language))
        return _ussd_response("CON", _kids_hub_menu(language))

    if flow == "kids_votd":
        language = _lang(session)
        age_band = str(session.get("age_band") or "6_9")
        reference = str(session.get("kids_votd_ref") or "Verse")
        verse_text = str(session.get("kids_votd_text") or "")
        topic = f"{reference}: {verse_text}"
        step = str(session.get("kids_close_step") or "choose")

        def _show_affirmation() -> PlainTextResponse:
            affirmation = kids_affirmation(
                topic, language=language, age_band=age_band
            )
            _set_flow(phone_number, "kids_hub", kids_close_step=None)
            return _ussd_response(
                "CON",
                f"{format_for_ussd(affirmation)}\n{_kids_hub_menu(language)}",
            )

        if step == "after_prayer":
            if action == "1":
                return _show_affirmation()
            return _ussd_response(
                "CON",
                f"{t(language, 'kids_pray')}\n"
                f"1. {t(language, 'kids_affirm')}\n"
                f"0. {t(language, 'home')}",
            )
        if action == "2":
            return _show_affirmation()
        if action == "1":
            prayer = kids_prayer(topic, language=language, age_band=age_band)
            _set_flow(phone_number, "kids_votd", kids_close_step="after_prayer")
            return _ussd_response(
                "CON",
                f"{format_for_ussd(prayer)}\n"
                f"1. {t(language, 'kids_affirm')}\n"
                f"0. {t(language, 'home')}",
            )
        return _open_kids_votd(phone_number, session)

    if flow == "kids_testament":
        language = _lang(session)
        if action == "1":
            session = _set_flow(
                phone_number, "kids_stories", kids_testament="old"
            )
            return _ussd_response("CON", _story_menu(session))
        if action == "2":
            session = _set_flow(
                phone_number, "kids_stories", kids_testament="new"
            )
            return _ussd_response("CON", _story_menu(session))
        return _ussd_response("CON", _kids_testament_menu(language))

    if flow == "kids_stories":
        return _pick_story_from_menu(phone_number, session, action)

    if flow == "kids_plans":
        language = _lang(session)
        topics = list_plan_topics()
        try:
            choice = int(action)
        except ValueError:
            return _ussd_response("CON", _kids_plans_menu(language))
        if choice < 1 or choice > len(topics):
            return _ussd_response("CON", _kids_plans_menu(language))
        plan_id, _label = topics[choice - 1]
        session = _set_flow(
            phone_number,
            "kids_plan_day",
            kids_plan_id=plan_id,
            kids_plan_day=1,
        )
        return _serve_kids_plan_day(phone_number, session)

    if flow == "kids_plan_day":
        language = _lang(session)
        plan_id = str(session.get("kids_plan_id") or "kindness")
        day = int(session.get("kids_plan_day") or 1)
        if action == "1":
            try:
                total = kids_plan_day_count(plan_id)
            except ValueError:
                _set_flow(phone_number, "kids_plans")
                return _ussd_response("CON", _kids_plans_menu(language))
            if day < total:
                session = _set_flow(
                    phone_number, "kids_plan_day", kids_plan_day=day + 1
                )
                return _serve_kids_plan_day(phone_number, session)
            _set_flow(phone_number, "kids_hub")
            return _ussd_response(
                "CON",
                f"{t(language, 'kids_plan_finished', title=topic_label(plan_id))}\n"
                f"{_kids_hub_menu(language)}",
            )
        return _serve_kids_plan_day(phone_number, session)

    if flow == "kids_got_it":
        if action == "2":
            story_id = str(session.get("kids_story_id") or "")
            section_index = int(session.get("kids_section") or 0)
            age_band = str(session.get("age_band") or "6_9")
            language = str(session.get("language") or "en")
            try:
                english = get_section(story_id, section_index)
            except ValueError:
                return _enter_kids(phone_number, session)
            simpler = simplify_for_kid(
                english, language=language, age_band=age_band
            )
            return _ussd_response("CON", _got_it_menu(simpler, language))
        if action == "1":
            story_id = str(session.get("kids_story_id") or "")
            section_index = int(session.get("kids_section") or 0)
            total = section_count(story_id)
            next_index = section_index + 1
            if next_index >= total:
                return _start_quiz(phone_number, session)
            session = _set_flow(
                phone_number, "kids_got_it", kids_section=next_index
            )
            return _present_kids_section(phone_number, session)
        return _present_kids_section(phone_number, session)

    if flow == "kids_quiz":
        language = _lang(session)
        story_id = str(session.get("kids_story_id") or "")
        age_band = str(session.get("age_band") or "6_9")
        index = int(session.get("kids_quiz_index") or 0)
        retries = int(session.get("kids_quiz_retries") or 0)
        questions = get_quiz_questions(story_id, age_band)
        if index >= len(questions):
            return _offer_kids_story_close(
                phone_number, session, "amazing_done"
            )
        question = questions[index]
        try:
            choice = int(action)
        except ValueError:
            return _quiz_prompt(session)
        if choice < 1 or choice > len(question["choices"]):
            return _quiz_prompt(session)
        if choice == int(question["answer"]):
            next_q = index + 1
            if next_q >= len(questions):
                return _offer_kids_story_close(
                    phone_number, session, "quiz_finished"
                )
            _set_flow(
                phone_number,
                "kids_quiz",
                kids_quiz_index=next_q,
                kids_quiz_retries=0,
            )
            return _quiz_prompt(get_user_session(phone_number))
        if retries < 1:
            _set_flow(phone_number, "kids_quiz", kids_quiz_retries=retries + 1)
            hint = question.get("hint") or "Try again!"
            return _ussd_response(
                "CON",
                format_for_ussd(t(language, "almost", hint=hint))
                + "\n"
                + "\n".join(
                    f"{i}. {c}"
                    for i, c in enumerate(question["choices"], start=1)
                )
                + f"\n{nav_footer(language)}",
            )
        correct = question["choices"][int(question["answer"]) - 1]
        next_q = index + 1
        if next_q >= len(questions):
            return _offer_kids_story_close(
                phone_number,
                session,
                "story_done",
                answer=correct,
            )
        _set_flow(
            phone_number,
            "kids_quiz",
            kids_quiz_index=next_q,
            kids_quiz_retries=0,
        )
        return _ussd_response(
            "CON",
            format_for_ussd(t(language, "answer_was", answer=correct))
            + "\n"
            + _quiz_text(get_user_session(phone_number)),
        )

    if flow == "kids_close":
        language = _lang(session)
        age_band = str(session.get("age_band") or "6_9")
        story_id = str(session.get("kids_story_id") or "")
        try:
            title = get_story(story_id)["title"]
        except ValueError:
            title = "this story"
        step = str(session.get("kids_close_step") or "choose")

        def _show_story_affirmation() -> PlainTextResponse:
            affirmation = kids_affirmation(
                title, language=language, age_band=age_band
            )
            _set_flow(phone_number, "kids_hub", kids_close_step=None)
            return _ussd_response(
                "CON",
                f"{format_for_ussd(affirmation)}\n{_kids_hub_menu(language)}",
            )

        if step == "after_prayer":
            if action == "1":
                return _show_story_affirmation()
            return _ussd_response(
                "CON",
                f"1. {t(language, 'kids_affirm')}\n0. {t(language, 'home')}",
            )
        if action == "2":
            return _show_story_affirmation()
        if action == "1":
            prayer = kids_prayer(title, language=language, age_band=age_band)
            _set_flow(phone_number, "kids_close", kids_close_step="after_prayer")
            return _ussd_response(
                "CON",
                f"{format_for_ussd(prayer)}\n"
                f"1. {t(language, 'kids_affirm')}\n"
                f"0. {t(language, 'home')}",
            )
        return _ussd_response(
            "CON",
            _kids_close_menu(language, t(language, "quiz_finished")),
        )


    return _show_main(phone_number)


@router.post("/ussd", response_class=PlainTextResponse)
def handle_ussd(
    session_id: Annotated[str, Form(alias="sessionId")],
    phone_number: Annotated[str, Form(alias="phoneNumber")],
    service_code: Annotated[str, Form(alias="serviceCode")],
    # First dial from Africa's Talking / the simulator sends an empty text
    # field; treat missing/blank as "" so validation does not 422.
    text: Annotated[str, Form()] = "",
) -> PlainTextResponse:
    """Handle one Africa's Talking USSD callback with Kids Corner support."""

    _ = session_id, service_code
    session = get_user_session(phone_number)
    selections = _parse_selections(text)

    if not session.get("language_set"):
        if not selections:
            _set_flow(phone_number, "lang")
            return _ussd_response("CON", _language_menu(welcome=True))
        return _apply_language(phone_number, _last_action(selections), then_main=True)

    if not selections:
        return _show_main(phone_number)

    # New dial after language is set always lands on main via empty text.
    # Subsequent keys use Redis flow + latest digit so Home works mid-path.
    action = _last_action(selections)
    session = get_user_session(phone_number)
    if str(session.get("ussd_flow") or "boot") in {"boot", ""}:
        _set_flow(phone_number, "main")
        session = get_user_session(phone_number)
    return _handle_flow(phone_number, session, action)
