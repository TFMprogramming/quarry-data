"""Figures from SEC XBRL company facts."""
from __future__ import annotations

import re
from dataclasses import dataclass

REVENUE_CONCEPTS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
]
QUARTER_FRAME = re.compile(r"^CY(\d{4})Q([1-4])$")


@dataclass
class Quarter:
    period: str  # "2026-Q2"
    revenue: float | None
    net_income: float | None


def public_float(facts: dict) -> float | None:
    values = facts.get("facts", {}).get("dei", {}).get("EntityPublicFloat", {}).get("units", {}).get("USD", [])
    values = [entry for entry in values if entry.get("val", 0) > 0]
    if not values:
        return None
    return float(max(values, key=lambda entry: entry.get("filed", ""))["val"])


def quarters(facts: dict, count: int = 8) -> list[Quarter]:
    revenue = _quarterly(facts, REVENUE_CONCEPTS)
    income = _quarterly(facts, ["NetIncomeLoss"])
    periods = sorted(set(revenue) | set(income))[-count:]
    return [Quarter(period, revenue.get(period), income.get(period)) for period in periods]


def revenue_growth(facts: dict) -> tuple[str, float] | None:
    """Latest quarter's revenue growth against the same quarter a year earlier."""
    revenue = _quarterly(facts, REVENUE_CONCEPTS)
    if not revenue:
        return None
    latest = max(revenue)
    year, quarter = latest.split("-")
    previous = revenue.get(f"{int(year) - 1}-{quarter}")
    if not previous or previous <= 0:
        return None
    return latest, revenue[latest] / previous - 1


def _quarterly(facts: dict, concepts: list[str]) -> dict[str, float]:
    """Quarter -> value. Earlier concepts win; later ones fill gaps (companies switch concepts over time)."""
    gaap = facts.get("facts", {}).get("us-gaap", {})
    series: dict[str, float] = {}
    for concept in concepts:
        for entry in gaap.get(concept, {}).get("units", {}).get("USD", []):
            match = QUARTER_FRAME.match(entry.get("frame", ""))
            if match:
                series.setdefault(f"{match.group(1)}-Q{match.group(2)}", float(entry["val"]))
    return series
