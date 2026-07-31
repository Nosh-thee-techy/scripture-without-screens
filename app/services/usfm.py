"""USFM helpers for human-readable Bible references on feature phones."""

from __future__ import annotations


# Common English book titles for USFM ids returned by YouVersion.
USFM_BOOK_TITLES: dict[str, str] = {
    "GEN": "Genesis",
    "EXO": "Exodus",
    "LEV": "Leviticus",
    "NUM": "Numbers",
    "DEU": "Deuteronomy",
    "JOS": "Joshua",
    "JDG": "Judges",
    "RUT": "Ruth",
    "1SA": "1 Samuel",
    "2SA": "2 Samuel",
    "1KI": "1 Kings",
    "2KI": "2 Kings",
    "1CH": "1 Chronicles",
    "2CH": "2 Chronicles",
    "EZR": "Ezra",
    "NEH": "Nehemiah",
    "EST": "Esther",
    "JOB": "Job",
    "PSA": "Psalms",
    "PRO": "Proverbs",
    "ECC": "Ecclesiastes",
    "SNG": "Song of Songs",
    "ISA": "Isaiah",
    "JER": "Jeremiah",
    "LAM": "Lamentations",
    "EZK": "Ezekiel",
    "DAN": "Daniel",
    "HOS": "Hosea",
    "JOL": "Joel",
    "AMO": "Amos",
    "OBA": "Obadiah",
    "JON": "Jonah",
    "MIC": "Micah",
    "NAM": "Nahum",
    "HAB": "Habakkuk",
    "ZEP": "Zephaniah",
    "HAG": "Haggai",
    "ZEC": "Zechariah",
    "MAL": "Malachi",
    "MAT": "Matthew",
    "MRK": "Mark",
    "LUK": "Luke",
    "JHN": "John",
    "ACT": "Acts",
    "ROM": "Romans",
    "1CO": "1 Corinthians",
    "2CO": "2 Corinthians",
    "GAL": "Galatians",
    "EPH": "Ephesians",
    "PHP": "Philippians",
    "COL": "Colossians",
    "1TH": "1 Thessalonians",
    "2TH": "2 Thessalonians",
    "1TI": "1 Timothy",
    "2TI": "2 Timothy",
    "TIT": "Titus",
    "PHM": "Philemon",
    "HEB": "Hebrews",
    "JAS": "James",
    "1PE": "1 Peter",
    "2PE": "2 Peter",
    "1JN": "1 John",
    "2JN": "2 John",
    "3JN": "3 John",
    "JUD": "Jude",
    "REV": "Revelation",
}


def book_title(usfm_book: str) -> str:
    """Return a display title for a USFM book code."""

    return USFM_BOOK_TITLES.get(usfm_book.upper(), usfm_book.upper())


def format_usfm_reference(passage_id: str) -> str:
    """Convert ``PRO.18.21`` / ``PSA.23`` / ``MAT.6.19-21`` to a readable cite.

    Args:
        passage_id: YouVersion USFM passage id.

    Returns:
        A citation such as ``Proverbs 18:21``.
    """

    parts = passage_id.strip().upper().split(".")
    if not parts:
        return passage_id
    title = book_title(parts[0])
    if len(parts) == 1:
        return title
    chapter = parts[1]
    if len(parts) == 2:
        return f"{title} {chapter}"
    verse = parts[2]
    return f"{title} {chapter}:{verse}"


def parse_usfm(passage_id: str) -> tuple[str, int | None, str | None]:
    """Split a passage id into book, chapter, and verse fragment.

    Returns:
        ``(book_usfm, chapter_number_or_None, verse_part_or_None)``.
    """

    parts = passage_id.strip().upper().split(".")
    book = parts[0] if parts else ""
    chapter: int | None = None
    verse: str | None = None
    if len(parts) >= 2 and parts[1].isdigit():
        chapter = int(parts[1])
    if len(parts) >= 3:
        verse = parts[2]
    return book, chapter, verse


def chapter_passage_id(book_usfm: str, chapter: int) -> str:
    """Build a whole-chapter USFM id such as ``PSA.23``."""

    return f"{book_usfm.upper()}.{chapter}"


def verse_passage_id(book_usfm: str, chapter: int, verse: int) -> str:
    """Build a single-verse USFM id such as ``JHN.3.16``."""

    return f"{book_usfm.upper()}.{chapter}.{verse}"
