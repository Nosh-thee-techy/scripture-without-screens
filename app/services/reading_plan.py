"""Local reading-plan schedules for USSD and voice.

YouVersion Platform v1 does not expose reading-plan day content, so this module
stores approved USFM references. Passage text is still fetched live from
YouVersion using the subscriber's saved language and Bible version.
"""

from __future__ import annotations


# Short daily references sized for USSD screens after YouVersion returns text.
HOPE_KENYA_PLAN: dict[int, str] = {
    1: "PSA.23.1-3",
    2: "JHN.3.16",
    3: "PHP.4.6-7",
    4: "ISA.41.10",
    5: "MAT.11.28-30",
    6: "ROM.8.28",
    7: "JER.29.11",
}

STRENGTH_PLAN: dict[int, str] = {
    1: "JOS.1.9",
    2: "PSA.46.1-2",
    3: "ISA.40.31",
    4: "EPH.6.10-11",
    5: "2TI.1.7",
    6: "PSA.27.1",
    7: "PHP.4.13",
}

PEACE_PLAN: dict[int, str] = {
    1: "JHN.14.27",
    2: "PSA.4.8",
    3: "COL.3.15",
    4: "ISA.26.3",
    5: "MAT.5.9",
    6: "ROM.15.13",
    7: "PSA.29.11",
}

PLANS: dict[str, dict[int, str]] = {
    "hope-kenya": HOPE_KENYA_PLAN,
    "strength": STRENGTH_PLAN,
    "peace": PEACE_PLAN,
}

PLAN_LABELS: dict[str, str] = {
    "hope-kenya": "Hope Kenya",
    "strength": "Daily Strength",
    "peace": "Peace for Today",
}

# Stable order for USSD / voice menus.
PLAN_ORDER: tuple[str, ...] = ("hope-kenya", "strength", "peace")


def list_plans() -> list[tuple[str, str, int]]:
    """Return available plans as ``(plan_id, label, day_count)`` tuples.

    Returns:
        Plans in ``PLAN_ORDER`` for numbered menus.
    """

    return [
        (plan_id, PLAN_LABELS[plan_id], len(PLANS[plan_id]))
        for plan_id in PLAN_ORDER
    ]


def plan_label(plan_id: str) -> str:
    """Return a human-readable label for a plan id.

    Args:
        plan_id: Local plan identifier.

    Returns:
        Display name, or the raw id if unknown.
    """

    return PLAN_LABELS.get(plan_id, plan_id)


def get_plan_reference(plan_id: str, day_number: int) -> str:
    """Return the USFM reference for one day of a local reading plan.

    Args:
        plan_id: Local plan identifier such as ``"hope-kenya"``.
        day_number: One-based day within the plan.

    Returns:
        A USFM passage ID such as ``"JHN.3.16"``.

    Raises:
        ValueError: If the plan or day is unknown.
    """

    schedule = PLANS.get(plan_id)
    if schedule is None:
        raise ValueError(f"Unknown reading plan '{plan_id}'.")
    if day_number not in schedule:
        raise ValueError(f"Day {day_number} is outside the {plan_id} plan.")
    return schedule[day_number]


def next_plan_day(plan_id: str, day_number: int) -> int:
    """Advance to the next plan day, wrapping after the final day.

    Args:
        plan_id: Local plan identifier used to look up length.
        day_number: Current one-based plan day.

    Returns:
        The following day number, or ``1`` after the last day.
    """

    schedule = PLANS.get(plan_id) or HOPE_KENYA_PLAN
    total_days = len(schedule)
    if day_number >= total_days:
        return 1
    return day_number + 1
