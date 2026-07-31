"""Local Kids Corner stories, topic reading plans, and age-banded quizzes.

YouVersion Platform does not expose kids plans or stories, so this module
stores short, feature-phone-friendly narratives. Optional USFM references can
still be fetched live from YouVersion when licensed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import PUBLIC_BASE_URL


AGE_BANDS: list[tuple[str, str]] = [
    ("u6", "Under 6"),
    ("6_9", "Ages 6-9"),
    ("10_12", "Ages 10-12"),
]

AGE_BAND_CODES = {code for code, _label in AGE_BANDS}

# Topic reading plans (separate from Bible stories).
KIDS_PLAN_TOPICS: list[tuple[str, str]] = [
    ("kindness", "Kindness"),
    ("fruit", "Fruits of the Spirit"),
    ("christmas", "Christmas"),
    ("easter", "Easter"),
    ("miracles", "Miracles of Jesus"),
]


def _q(
    question: str, choices: list[str], answer: int = 1, hint: str = ""
) -> dict[str, Any]:
    """Build one quiz item."""

    return {
        "q": question,
        "choices": choices,
        "answer": answer,
        "hint": hint or "Try again!",
    }


def _simple_quiz(
    q1: tuple[str, list[str], str],
    q2: tuple[str, list[str], str],
    q3: tuple[str, list[str], str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Build u6 / 6_9 / 10_12 quizzes from short tuples."""

    def pack(items: list[tuple[str, list[str], str]]) -> list[dict[str, Any]]:
        return [_q(q, choices, 1, hint) for q, choices, hint in items]

    base = [q1, q2]
    older = base + ([q3] if q3 else [])
    return {
        "u6": pack(base),
        "6_9": pack(older),
        "10_12": pack(older),
    }


STORIES: dict[str, dict[str, Any]] = {
    "noah": {
        "id": "noah",
        "title": "Noah's big boat",
        "testament": "old",
        "age_bands": ("u6", "6_9", "10_12"),
        "usfm": "GEN.7",
        "sections": [
            "God saw people being unkind. He asked Noah to build a very big boat.",
            "Noah trusted God. He built the boat and welcomed animals two by two.",
            "Rain fell, then stopped. God kept Noah's family safe. A rainbow said God cares.",
        ],
        "quizzes": _simple_quiz(
            ("Who built the big boat?", ["Noah", "A giant", "A fish"], "God asked Noah."),
            ("What showed God cares?", ["A rainbow", "A drum", "A kite"], "Look after the rain!"),
            ("Best lesson?", ["Trust God in hard times", "Boats are toys", "Ignore others"], "Faith in storms."),
        ),
    },
    "david": {
        "id": "david",
        "title": "David and the giant",
        "testament": "old",
        "age_bands": ("u6", "6_9", "10_12"),
        "usfm": "1SA.17",
        "sections": [
            "A huge giant named Goliath scared God's people. Young David was brave.",
            "David said God would help. He took a sling and five smooth stones.",
            "David trusted God, not fancy armor. The giant fell. God gave courage.",
        ],
        "quizzes": _simple_quiz(
            ("Who was brave?", ["David", "Goliath", "A sheep"], "A young shepherd."),
            ("Who helped David?", ["God", "A robot", "Luck"], "David trusted God."),
            ("Main lesson?", ["God gives courage", "Giants always win", "Never try"], "Be brave with God."),
        ),
    },
    "joseph": {
        "id": "joseph",
        "title": "Joseph's colorful coat",
        "testament": "old",
        "age_bands": ("u6", "6_9", "10_12"),
        "usfm": "GEN.37",
        "sections": [
            "Jacob loved Joseph and gave him a bright coat. His brothers were jealous.",
            "They sent Joseph away. God stayed with Joseph in hard places.",
            "Later Joseph forgave them and helped his family. God can turn hurt into help.",
        ],
        "quizzes": _simple_quiz(
            ("Who got a colorful coat?", ["Joseph", "A king", "A lion"], "Jacob's son."),
            ("What did Joseph do later?", ["Forgave his brothers", "Hid forever", "Tore the coat"], "He chose mercy."),
            ("Lesson?", ["God is with us in hard times", "Jealousy is good", "Never forgive"], "Trust God's plan."),
        ),
    },
    "moses": {
        "id": "moses",
        "title": "Moses and the sea",
        "testament": "old",
        "age_bands": ("u6", "6_9", "10_12"),
        "usfm": "EXO.14",
        "sections": [
            "God's people were trapped by the sea. Pharaoh's army chased them.",
            "Moses trusted God. God made a dry path through the water.",
            "Everyone walked safely. God rescues people who trust Him.",
        ],
        "quizzes": _simple_quiz(
            ("Who led the people?", ["Moses", "A whale", "Pharaoh"], "God's helper."),
            ("What did God open?", ["A path in the sea", "A shop", "A cave only"], "Water made a road."),
            ("Lesson?", ["God makes a way", "Give up at water", "Run alone"], "Trust when stuck."),
        ),
    },
    "daniel": {
        "id": "daniel",
        "title": "Daniel and the lions",
        "testament": "old",
        "age_bands": ("6_9", "10_12"),
        "usfm": "DAN.6",
        "sections": [
            "Daniel prayed to God every day, even when a rule said stop.",
            "He was put in a den of lions. God sent an angel to shut their mouths.",
            "Daniel was safe. Praying to God is brave and good.",
        ],
        "quizzes": _simple_quiz(
            ("Who prayed every day?", ["Daniel", "A lion", "A guard"], "A faithful man."),
            ("Who kept Daniel safe?", ["God", "The lions' lunch", "A net"], "An angel helped."),
            ("Lesson?", ["Keep praying", "Hide from God", "Fear always wins"], "Faith over fear."),
        ),
    },
    "jonah": {
        "id": "jonah",
        "title": "Jonah and the big fish",
        "testament": "old",
        "age_bands": ("u6", "6_9", "10_12"),
        "usfm": "JON.1",
        "sections": [
            "God told Jonah to go help a city. Jonah ran the other way on a boat.",
            "A storm came. Jonah was swallowed by a big fish. He prayed inside.",
            "God gave Jonah another chance. Obeying God is better than running.",
        ],
        "quizzes": _simple_quiz(
            ("Who ran from God?", ["Jonah", "A fish", "A sailor only"], "A prophet who fled."),
            ("Where did Jonah pray?", ["Inside a big fish", "On a throne", "In a shop"], "God still heard him."),
            ("Lesson?", ["God gives second chances", "Always run", "Ignore God"], "Turn back to God."),
        ),
    },
    "samaritan": {
        "id": "samaritan",
        "title": "The kind stranger",
        "testament": "new",
        "age_bands": ("6_9", "10_12"),
        "usfm": "LUK.10",
        "sections": [
            "A man was hurt on the road. Some people walked past and did not help.",
            "A stranger from another place stopped. He cleaned the wounds and cared.",
            "Jesus said: love your neighbor. Kindness is for everyone, even strangers.",
        ],
        "quizzes": _simple_quiz(
            ("Who helped the hurt man?", ["A kind stranger", "Nobody", "A bird"], "Someone stopped."),
            ("What should we do?", ["Be kind to others", "Walk past always", "Laugh"], "Love your neighbor."),
            ("Neighbor means?", ["Anyone we can help", "Only family", "Only friends"], "Jesus widened the circle."),
        ),
    },
    "calms_storm": {
        "id": "calms_storm",
        "title": "Jesus calms the storm",
        "testament": "new",
        "age_bands": ("u6", "6_9", "10_12"),
        "usfm": "MRK.4",
        "sections": [
            "Jesus and friends were in a boat. A wild storm scared everyone.",
            "Jesus spoke to the wind and waves: Be still! The sea became quiet.",
            "Jesus has power to bring peace when we are afraid.",
        ],
        "quizzes": _simple_quiz(
            ("Who calmed the storm?", ["Jesus", "A sailor", "A cloud"], "He spoke peace."),
            ("What did the sea do?", ["Became quiet", "Got bigger", "Turned pink"], "Wind and waves stopped."),
            ("Lesson?", ["Jesus brings peace", "Fear wins", "Boats are bad"], "Ask Him when afraid."),
        ),
    },
    "loaves": {
        "id": "loaves",
        "title": "Bread and fish for many",
        "testament": "new",
        "age_bands": ("u6", "6_9", "10_12"),
        "usfm": "JHN.6",
        "sections": [
            "A big crowd was hungry. A boy shared five loaves and two fish.",
            "Jesus thanked God and shared the food. Everyone had enough to eat.",
            "When we share, God can do more than we imagine.",
        ],
        "quizzes": _simple_quiz(
            ("Who shared food?", ["A boy", "A giant", "Nobody"], "Small gift, big help."),
            ("What did Jesus do?", ["Fed many people", "Hid the food", "Sent them away hungry"], "He multiplied it."),
            ("Lesson?", ["Sharing matters", "Keep all food", "Crowds are bad"], "Give what you have."),
        ),
    },
    "zacchaeus": {
        "id": "zacchaeus",
        "title": "Zacchaeus in the tree",
        "testament": "new",
        "age_bands": ("u6", "6_9", "10_12"),
        "usfm": "LUK.19",
        "sections": [
            "Short Zacchaeus climbed a tree to see Jesus walk by.",
            "Jesus looked up and said, Come down. I want to visit your house.",
            "Zacchaeus changed and shared. Jesus loves people who feel left out.",
        ],
        "quizzes": _simple_quiz(
            ("Where did Zacchaeus climb?", ["A tree", "A mountain of gold", "A cloud"], "To see Jesus."),
            ("Who wanted to visit him?", ["Jesus", "A tax boss", "A bird"], "Jesus called him."),
            ("Lesson?", ["Jesus welcomes everyone", "Hide in trees", "Never change"], "You matter to God."),
        ),
    },
    "christmas_birth": {
        "id": "christmas_birth",
        "title": "Baby Jesus is born",
        "testament": "new",
        "age_bands": ("u6", "6_9", "10_12"),
        "usfm": "LUK.2",
        "sections": [
            "Mary and Joseph traveled to Bethlehem. There was no room in the inn.",
            "Baby Jesus was born and laid in a manger. Angels told shepherds the good news.",
            "Christmas means God sent Jesus because He loves the world.",
        ],
        "quizzes": _simple_quiz(
            ("Who was born at Christmas?", ["Jesus", "A king in a castle only", "A star"], "God's Son."),
            ("Who heard angels?", ["Shepherds", "Only rich people", "Lions"], "Good news for all."),
            ("Christmas means?", ["God sent Jesus in love", "Only gifts", "Only food"], "Love came near."),
        ),
    },
    "easter_risen": {
        "id": "easter_risen",
        "title": "Jesus is alive",
        "testament": "new",
        "age_bands": ("u6", "6_9", "10_12"),
        "usfm": "JHN.20",
        "sections": [
            "Jesus died on a cross. Friends were very sad.",
            "On the third day the tomb was empty. Jesus is alive!",
            "Easter means hope: Jesus beat death and shares new life with us.",
        ],
        "quizzes": _simple_quiz(
            ("What happened at Easter?", ["Jesus rose", "Winter came", "Boats sank"], "He is alive."),
            ("Was the tomb empty?", ["Yes", "No", "Full of gold"], "Good news!"),
            ("Easter means?", ["Hope and new life", "Only candy", "Be sad forever"], "Jesus wins."),
        ),
    },
}


KIDS_PLANS: dict[str, dict[str, Any]] = {
    "kindness": {
        "id": "kindness",
        "title": "Kindness",
        "days": [
            {
                "title": "Share a smile",
                "text": "Kindness can be a smile, a share, or a soft word. God loves kind hearts.",
                "usfm": "EPH.4.32",
            },
            {
                "title": "Help a friend",
                "text": "When someone is sad or hurt, stop and help like the kind stranger Jesus praised.",
                "usfm": "LUK.10.33",
            },
            {
                "title": "Be gentle",
                "text": "Gentle words are strong. Speak peace at home and at school.",
                "usfm": "PRO.15.1",
            },
        ],
    },
    "fruit": {
        "id": "fruit",
        "title": "Fruits of the Spirit",
        "days": [
            {
                "title": "Love & joy",
                "text": "God's Spirit grows love and joy in us — like sweet fruit on a tree.",
                "usfm": "GAL.5.22",
            },
            {
                "title": "Peace & patience",
                "text": "Peace stays calm. Patience waits without shouting. Ask God to help you grow.",
                "usfm": "GAL.5.22",
            },
            {
                "title": "Kindness & goodness",
                "text": "Kindness and goodness show others what God is like.",
                "usfm": "GAL.5.22",
            },
            {
                "title": "Faith & self-control",
                "text": "Faith trusts God. Self-control chooses the good path even when it is hard.",
                "usfm": "GAL.5.23",
            },
        ],
    },
    "christmas": {
        "id": "christmas",
        "title": "Christmas",
        "days": [
            {
                "title": "A promise comes",
                "text": "Long ago God promised a Savior. Christmas is that promise arriving.",
                "usfm": "ISA.9.6",
            },
            {
                "title": "Born in Bethlehem",
                "text": "Jesus was born in a humble place. God came near to ordinary people.",
                "usfm": "LUK.2.7",
            },
            {
                "title": "Good news for all",
                "text": "Angels sang: peace on earth. Christmas is joy for every family.",
                "usfm": "LUK.2.10",
            },
        ],
    },
    "easter": {
        "id": "easter",
        "title": "Easter",
        "days": [
            {
                "title": "Jesus loves us",
                "text": "Jesus gave His life because He loves us so much.",
                "usfm": "JHN.3.16",
            },
            {
                "title": "The empty tomb",
                "text": "Friends found the tomb empty. Jesus is alive — that is Easter!",
                "usfm": "LUK.24.6",
            },
            {
                "title": "Hope forever",
                "text": "Because Jesus lives, we have hope when we are scared or sad.",
                "usfm": "JHN.11.25",
            },
        ],
    },
    "miracles": {
        "id": "miracles",
        "title": "Miracles of Jesus",
        "days": [
            {
                "title": "Storm, be still",
                "text": "Jesus spoke to a storm and it became quiet. He brings peace.",
                "usfm": "MRK.4.39",
            },
            {
                "title": "Food for many",
                "text": "Jesus fed a hungry crowd from a small lunch. He cares when we need help.",
                "usfm": "JHN.6.11",
            },
            {
                "title": "A man can walk",
                "text": "Jesus healed people who could not walk. He is kind and powerful.",
                "usfm": "MRK.2.12",
            },
            {
                "title": "Believe",
                "text": "Miracles show who Jesus is. We can trust Him with our worries.",
                "usfm": "JHN.20.31",
            },
        ],
    },
}


_STORY_ORDER = (
    "noah",
    "david",
    "joseph",
    "moses",
    "daniel",
    "jonah",
    "samaritan",
    "calms_storm",
    "loaves",
    "zacchaeus",
    "christmas_birth",
    "easter_risen",
)


def list_plan_topics() -> list[tuple[str, str]]:
    """Return kids reading-plan topic codes and English labels."""

    return list(KIDS_PLAN_TOPICS)


def get_kids_plan(plan_id: str) -> dict[str, Any]:
    """Load one kids reading plan.

    Raises:
        ValueError: If the plan id is unknown.
    """

    plan = KIDS_PLANS.get(plan_id)
    if plan is None:
        raise ValueError(f"Unknown kids plan '{plan_id}'.")
    return plan


def kids_plan_day_count(plan_id: str) -> int:
    """Return how many days a kids plan has."""

    return len(get_kids_plan(plan_id)["days"])


def get_kids_plan_day(plan_id: str, day_number: int) -> dict[str, Any]:
    """Return one plan day (1-based).

    Raises:
        ValueError: If the plan or day is invalid.
    """

    days = get_kids_plan(plan_id)["days"]
    if day_number < 1 or day_number > len(days):
        raise ValueError(f"Day {day_number} out of range for {plan_id}.")
    return days[day_number - 1]


def list_stories_for_age(
    age_band: str, testament: str | None = None
) -> list[dict[str, Any]]:
    """Return stories allowed for an age band, optionally filtered by testament.

    Args:
        age_band: One of ``u6``, ``6_9``, or ``10_12``.
        testament: ``old``, ``new``, or ``None`` for all.
    """

    wanted = None
    if testament in {"old", "ot", "old_testament"}:
        wanted = "old"
    elif testament in {"new", "nt", "new_testament"}:
        wanted = "new"

    results: list[dict[str, Any]] = []
    for story_id in _STORY_ORDER:
        story = STORIES[story_id]
        if age_band not in story["age_bands"]:
            continue
        if wanted and story.get("testament") != wanted:
            continue
        results.append(story)
    return results


def get_story(story_id: str) -> dict[str, Any]:
    """Load one story by id."""

    story = STORIES.get(story_id)
    if story is None:
        raise ValueError(f"Unknown kids story '{story_id}'.")
    return story


def get_section(story_id: str, section_index: int) -> str:
    """Return one story section body."""

    story = get_story(story_id)
    sections: list[str] = story["sections"]
    if section_index < 0 or section_index >= len(sections):
        raise ValueError(f"Section {section_index} out of range for {story_id}.")
    return sections[section_index]


def section_count(story_id: str) -> int:
    """Return how many sections a story has."""

    return len(get_story(story_id)["sections"])


def get_quiz_questions(story_id: str, age_band: str) -> list[dict[str, Any]]:
    """Return quiz questions for a story and age band."""

    story = get_story(story_id)
    quizzes = story["quizzes"].get(age_band)
    if not quizzes:
        for fallback in ("6_9", "10_12", "u6"):
            if story["quizzes"].get(fallback):
                return list(story["quizzes"][fallback])
        raise ValueError(f"No quiz for story '{story_id}'.")
    return list(quizzes)


def age_band_label(age_band: str) -> str:
    """Human label for an age band code."""

    for code, label in AGE_BANDS:
        if code == age_band:
            return label
    return age_band


def topic_label(topic_id: str) -> str:
    """English label for a kids plan topic."""

    for code, label in KIDS_PLAN_TOPICS:
        if code == topic_id:
            return label
    return topic_id


_KIDS_STATIC_DIR = Path(__file__).resolve().parent.parent / "static" / "kids"


def story_image_filename(story_id: str) -> str | None:
    """Local filename for a story cover (JPEG preferred, PNG fallback)."""

    if not story_id:
        return None
    for name in (f"{story_id}.jpg", f"{story_id}.png"):
        if (_KIDS_STATIC_DIR / name).is_file():
            return name
    return None


def story_image_path(story_id: str) -> Path | None:
    """Filesystem path for a story cover when an image file exists."""

    name = story_image_filename(story_id)
    if name is None:
        return None
    return _KIDS_STATIC_DIR / name


def story_image_url(story_id: str) -> str | None:
    """Public HTTPS URL for WhatsApp image messages when available.

    Requires ``PUBLIC_BASE_URL`` (ngrok) so Meta can fetch the image.
    """

    if not story_id or not PUBLIC_BASE_URL:
        return None
    name = story_image_filename(story_id)
    if name is None:
        return None
    return f"{PUBLIC_BASE_URL}/static/kids/{name}"


# Theme art for Kids VOTD / plans — matched to passage wording.
_THEME_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    (
        "kind_words",
        (
            "tongue",
            "word",
            "words",
            "speak",
            "speech",
            "lips",
            "mouth",
            "talk",
            "say",
            "said",
        ),
    ),
    ("love", ("love", "loved", "loving", "kind", "kindness", "mercy", "neighbor")),
    ("courage", ("courage", "strong", "strength", "fear", "afraid", "brave", "power")),
    ("peace", ("peace", "peaceful", "still", "calm", "rest", "quiet")),
    ("prayer", ("pray", "prayer", "prayed", "ask", "seek", "knock")),
    ("light", ("light", "lamp", "shine", "shines", "darkness", "bright")),
    ("calms_storm", ("storm", "wind", "waves", "sea", "boat")),
    ("loaves", ("bread", "loaves", "fish", "feed", "hungry")),
    ("shepherd", ("shepherd", "sheep", "psalm 23")),
    ("christmas_birth", ("born", "birth", "bethlehem", "manger", "christmas")),
    ("easter_risen", ("risen", "resurrection", "empty tomb", "easter", "alive")),
    ("samaritan", ("neighbor", "samaritan", "helped", "help")),
    ("noah", ("ark", "flood", "rainbow", "noah")),
    ("david", ("goliath", "sling", "david")),
    ("daniel", ("lion", "lions", "daniel")),
    ("jonah", ("whale", "fish", "jonah", "nineveh")),
    ("moses", ("egypt", "pharaoh", "moses", "red sea")),
    ("joseph", ("joseph", "dream", "brothers")),
    ("zacchaeus", ("zacchaeus", "tree", "tax")),
]


def pick_passage_theme(
    reference: str = "",
    text: str = "",
    passage_id: str = "",
) -> str:
    """Choose a kids visual theme id that fits the passage."""

    haystack = f"{reference} {text} {passage_id}".lower()
    for theme_id, keywords in _THEME_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            if story_image_filename(theme_id):
                return theme_id
    # Soft book-level fallbacks.
    book = (passage_id or reference).upper()
    if book.startswith(("PSA", "PSALM")):
        return "peace" if story_image_filename("peace") else "light"
    if book.startswith(("PRO", "PROVERB")):
        return "kind_words" if story_image_filename("kind_words") else "light"
    if book.startswith(("JHN", "MAT", "MRK", "LUK", "JOHN", "MATT", "MARK", "LUKE")):
        return "love" if story_image_filename("love") else "loaves"
    if book.startswith(("GEN",)):
        return "noah" if story_image_filename("noah") else "light"
    return "light" if story_image_filename("light") else "loaves"


def passage_image_url(
    reference: str = "",
    text: str = "",
    passage_id: str = "",
) -> str | None:
    """Public image URL matched to a kids passage theme."""

    return story_image_url(pick_passage_theme(reference, text, passage_id))
