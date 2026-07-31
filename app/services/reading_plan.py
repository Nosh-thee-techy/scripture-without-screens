"""Category-filtered reading plans for USSD and voice.

YouVersion Platform v1 does not expose reading-plan catalogs or day schedules
(confirmed: /v1/plans and related paths return 404). This module mirrors
YouVersion-style topic filters locally. Passage text is still fetched live from
YouVersion using the subscriber's saved language and Bible version.
"""

from __future__ import annotations

from typing import Any


# Topic filters inspired by common YouVersion plan browsing themes.
CATEGORIES: list[tuple[str, str]] = [
    ("hope", "Hope"),
    ("sadness", "Sadness"),
    ("wealth", "Wealth"),
    ("strength", "Strength"),
    ("peace", "Peace"),
    ("anxiety", "Anxiety"),
]

CATEGORY_LABELS = {code: label for code, label in CATEGORIES}


PLANS: dict[str, dict[str, Any]] = {
    "hope-kenya": {
        "id": "hope-kenya",
        "title": "Hope Kenya",
        "category": "hope",
        "about": (
            "Seven days of hope when life feels uncertain. God stays near and "
            "keeps His promises."
        ),
        "days": {
            1: "PSA.23.1-3",
            2: "JHN.3.16",
            3: "PHP.4.6-7",
            4: "ISA.41.10",
            5: "MAT.11.28-30",
            6: "ROM.8.28",
            7: "JER.29.11",
        },
    },
    "hope-rising": {
        "id": "hope-rising",
        "title": "Hope Rising",
        "category": "hope",
        "about": (
            "Short readings that lift your eyes when tomorrow looks heavy. "
            "Hope is a Person, not a wish."
        ),
        "days": {
            1: "ROM.15.13",
            2: "PSA.42.5",
            3: "LAM.3.22-23",
            4: "HEB.6.19",
            5: "1PE.1.3",
        },
    },
    "comfort-tears": {
        "id": "comfort-tears",
        "title": "Comfort in Tears",
        "category": "sadness",
        "about": (
            "For heavy hearts. God sees your tears and draws close to the "
            "brokenhearted."
        ),
        "days": {
            1: "PSA.34.18",
            2: "MAT.5.4",
            3: "2CO.1.3-4",
            4: "PSA.147.3",
            5: "REV.21.4",
        },
    },
    "god-near-pain": {
        "id": "god-near-pain",
        "title": "God Near in Pain",
        "category": "sadness",
        "about": (
            "When grief is loud, these verses remind you that you are not alone "
            "in the dark."
        ),
        "days": {
            1: "PSA.23.4",
            2: "ISA.43.2",
            3: "JHN.14.1",
            4: "PSA.56.8",
            5: "ROM.8.38-39",
        },
    },
    "true-riches": {
        "id": "true-riches",
        "title": "True Riches",
        "category": "wealth",
        "about": (
            "What is real wealth? Scripture on generosity, contentment, and "
            "treasure that lasts."
        ),
        "days": {
            1: "MAT.6.19-21",
            2: "1TI.6.6-8",
            3: "PRO.3.9-10",
            4: "LUK.12.15",
            5: "2CO.9.7-8",
        },
    },
    "wise-with-money": {
        "id": "wise-with-money",
        "title": "Wise With Money",
        "category": "wealth",
        "about": (
            "Practical wisdom for work, giving, and trusting God more than "
            "coins in hand."
        ),
        "days": {
            1: "PRO.22.1",
            2: "HEB.13.5",
            3: "MAL.3.10",
            4: "ECC.5.10",
            5: "MAT.6.33",
        },
    },
    "strength": {
        "id": "strength",
        "title": "Daily Strength",
        "category": "strength",
        "about": (
            "Courage for hard days. God gives strength when yours runs out."
        ),
        "days": {
            1: "JOS.1.9",
            2: "PSA.46.1-2",
            3: "ISA.40.31",
            4: "EPH.6.10-11",
            5: "2TI.1.7",
            6: "PSA.27.1",
            7: "PHP.4.13",
        },
    },
    "peace": {
        "id": "peace",
        "title": "Peace for Today",
        "category": "peace",
        "about": (
            "Calm for restless minds. Jesus gives peace the world cannot copy."
        ),
        "days": {
            1: "JHN.14.27",
            2: "PSA.4.8",
            3: "COL.3.15",
            4: "ISA.26.3",
            5: "MAT.5.9",
            6: "ROM.15.13",
            7: "PSA.29.11",
        },
    },
    "anxiety-rest": {
        "id": "anxiety-rest",
        "title": "Rest From Worry",
        "category": "anxiety",
        "about": (
            "When thoughts race, cast your cares on God who cares for you."
        ),
        "days": {
            1: "1PE.5.7",
            2: "PHP.4.6-7",
            3: "MAT.6.25-27",
            4: "PSA.55.22",
            5: "JHN.14.27",
        },
    },
}


HOPE_KENYA_PLAN = PLANS["hope-kenya"]["days"]
STRENGTH_PLAN = PLANS["strength"]["days"]
PEACE_PLAN = PLANS["peace"]["days"]
PLAN_ORDER = tuple(PLANS.keys())
PLAN_LABELS = {plan_id: plan["title"] for plan_id, plan in PLANS.items()}


def list_categories() -> list[tuple[str, str]]:
    """Return ``(category_id, label)`` pairs for USSD filter menus."""

    return list(CATEGORIES)


def category_label(category_id: str) -> str:
    """Human label for a category id."""

    return CATEGORY_LABELS.get(category_id, category_id)


def list_plans() -> list[tuple[str, str, int]]:
    """Return all plans as ``(plan_id, label, day_count)`` for legacy callers."""

    return [
        (plan_id, plan["title"], len(plan["days"]))
        for plan_id, plan in PLANS.items()
    ]


def list_plans_in_category(category_id: str) -> list[dict[str, Any]]:
    """Return plan dictionaries in one topic category."""

    return [
        plan
        for plan_id, plan in PLANS.items()
        if plan["category"] == category_id
    ]


def get_plan(plan_id: str) -> dict[str, Any]:
    """Load one plan document.

    Raises:
        ValueError: If the plan is unknown.
    """

    plan = PLANS.get(plan_id)
    if plan is None:
        raise ValueError(f"Unknown reading plan '{plan_id}'.")
    return plan


def plan_label(plan_id: str) -> str:
    """Return a human-readable label for a plan id."""

    plan = PLANS.get(plan_id)
    if plan is None:
        return plan_id
    return str(plan["title"])


def plan_day_count(plan_id: str) -> int:
    """Number of days in a plan."""

    return len(get_plan(plan_id)["days"])


def get_plan_reference(plan_id: str, day_number: int) -> str:
    """Return the USFM reference for one day of a reading plan."""

    plan = get_plan(plan_id)
    days: dict[int, str] = plan["days"]
    if day_number not in days:
        raise ValueError(f"Day {day_number} is outside the {plan_id} plan.")
    return days[day_number]


def next_plan_day(plan_id: str, day_number: int) -> int:
    """Advance to the next plan day, wrapping after the final day."""

    total_days = plan_day_count(plan_id)
    if day_number >= total_days:
        return 1
    return day_number + 1


def plan_overview_lines(plan_id: str, *, max_days_listed: int = 3) -> list[str]:
    """Build short overview lines: title, about, and sample day references."""

    plan = get_plan(plan_id)
    days: dict[int, str] = plan["days"]
    lines = [
        str(plan["title"]),
        str(plan["about"]),
        f"{len(days)} days. Sample refs:",
    ]
    for day_number in sorted(days)[:max_days_listed]:
        lines.append(f"D{day_number} {days[day_number]}")
    if len(days) > max_days_listed:
        lines.append(f"+{len(days) - max_days_listed} more days")
    return lines
