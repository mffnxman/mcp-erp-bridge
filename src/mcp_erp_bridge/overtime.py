"""Overtime walk-back recovery.

Field-service schedule exports commonly report a weekly total without flagging
which day pushed a worker past 40 hours. This module walks Friday
backwards (Fri -> Thu -> Wed -> Tue) applying hours until cumulative crosses
the threshold; the day where we cross is the 'primary overage day.'
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DAYS_REVERSE = ["Fri", "Thu", "Wed", "Tue", "Mon", "Sun", "Sat"]

Severity = Literal["low", "medium", "high"]


@dataclass
class OTBreakdown:
    total: float
    overtime: float
    primary_day: str | None


def compute_overtime(
    daily_hours: dict[str, float], threshold: float = 40.0
) -> OTBreakdown:
    """Return total, OT, and the day that pushed us over the threshold."""
    total = sum(daily_hours.values())
    overtime = max(0.0, total - threshold)
    if overtime == 0:
        return OTBreakdown(total=total, overtime=0.0, primary_day=None)

    cumulative = 0.0
    for day in DAYS_REVERSE:
        if day not in daily_hours:
            continue
        cumulative += daily_hours[day]
        if cumulative >= overtime:
            return OTBreakdown(total=total, overtime=overtime, primary_day=day)

    return OTBreakdown(total=total, overtime=overtime, primary_day="Fri")


def severity_from_overtime(overtime: float) -> Severity:
    if overtime >= 16:
        return "high"
    if overtime >= 8:
        return "medium"
    return "low"
