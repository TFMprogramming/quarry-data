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


CASH_CONCEPTS = ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
                 "Cash"]
SECURITIES_CONCEPTS = ["ShortTermInvestments", "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
                       "MarketableSecuritiesCurrent"]


def balance(facts: dict) -> dict | None:
    """Latest cash, debt and share count, plus cash flows of the last twelve months."""
    gaap = facts.get("facts", {}).get("us-gaap", {})
    cash = _latest_instant(gaap, CASH_CONCEPTS)
    operating = _trailing_year(gaap, "NetCashProvidedByUsedInOperatingActivities")
    investment = _trailing_year(gaap, "PaymentsToAcquirePropertyPlantAndEquipment")
    shares, shares_change = _shares(facts)
    if cash is None and operating is None and shares is None:
        return None

    result: dict = {"date": cash[0] if cash else None}
    if cash:
        securities = _instant_at(gaap, SECURITIES_CONCEPTS, cash[0])
        result["cash"] = cash[1] + (securities or 0)
    result["debt"] = _debt(gaap)
    result["shares"] = shares
    result["sharesChange"] = shares_change
    result["operatingCashFlow"] = operating
    result["freeCashFlow"] = operating - (investment or 0) if operating is not None else None
    return {key: value for key, value in result.items() if value is not None}


def _entries(gaap: dict, concept: str) -> list[dict]:
    return gaap.get(concept, {}).get("units", {}).get("USD", [])


def _latest_instant(gaap: dict, concepts: list[str]) -> tuple[str, float] | None:
    """(end date, value) of the newest instant value among the concepts; earlier concepts win ties."""
    best = None
    for concept in concepts:
        for entry in _entries(gaap, concept):
            if "start" not in entry or entry["start"] is None:
                if best is None or entry["end"] > best[0]:
                    best = (entry["end"], float(entry["val"]))
    return best


def _instant_at(gaap: dict, concepts: list[str], end: str) -> float | None:
    for concept in concepts:
        for entry in _entries(gaap, concept):
            if entry["end"] == end and not entry.get("start"):
                return float(entry["val"])
    return None


# Companies name their debt differently, and switch names over the years:
# a single total, or a long-term part plus the part due within a year.
DEBT_TOTALS = ["LongTermDebt", "DebtAndCapitalLeaseObligations", "DebtLongtermAndShorttermCombinedAmount",
               "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities"]
DEBT_PARTS = [("LongTermDebtNoncurrent", ["LongTermDebtCurrent", "DebtCurrent"]),
              ("LongTermDebtAndCapitalLeaseObligations", ["LongTermDebtAndCapitalLeaseObligationsCurrent", "DebtCurrent"])]


def _debt(gaap: dict) -> float | None:
    """Total financial debt at the newest date any of the known names reports it."""
    candidates = []
    for concept in DEBT_TOTALS:
        found = _latest_instant(gaap, [concept])
        if found:
            candidates.append(found)
    for long_term, current in DEBT_PARTS:
        found = _latest_instant(gaap, [long_term])
        if found:
            candidates.append((found[0], found[1] + (_instant_at(gaap, current, found[0]) or 0)))
    if not candidates:
        return None
    newest = max(end for end, _ in candidates)
    return next(value for end, value in candidates if end == newest)


def _trailing_year(gaap: dict, concept: str) -> float | None:
    """Cash flows are reported year to date; twelve months = this year so far
    + the last full fiscal year − the same part of that year."""
    entries = [e for e in _entries(gaap, concept) if e.get("start")]
    if not entries:
        return None
    latest = max(entries, key=lambda e: (e["end"], _days(e)))
    if _days(latest) >= 330:
        return float(latest["val"])
    for full in entries:
        if 330 <= _days(full) <= 380 and abs(_gap(full["end"], latest["start"])) <= 7:
            for earlier in entries:
                if earlier["start"] == full["start"] and abs(_days(earlier) - _days(latest)) <= 10:
                    return float(latest["val"] + full["val"] - earlier["val"])
    return None


def _shares(facts: dict) -> tuple[float | None, float | None]:
    """Shares outstanding from the cover page (all classes of one filing summed),
    and the change against roughly a year earlier."""
    entries = facts.get("facts", {}).get("dei", {}).get("EntityCommonStockSharesOutstanding", {}) \
        .get("units", {}).get("shares", [])
    totals: dict[tuple[str, str], float] = {}
    for entry in entries:
        key = (entry["end"], entry.get("accn", ""))
        totals[key] = totals.get(key, 0) + float(entry["val"])
    if not totals:
        return None, None
    by_date = {end: value for (end, _), value in sorted(totals.items())}
    latest_end = max(by_date)
    latest = by_date[latest_end]
    year_ago = [end for end in by_date if 300 <= _gap(end, latest_end) <= 430]
    if not year_ago or latest <= 0:
        return latest, None
    previous = by_date[min(year_ago, key=lambda end: abs(_gap(end, latest_end) - 365))]
    return latest, round(latest / previous - 1, 4) if previous > 0 else None


def _days(entry: dict) -> int:
    return _gap(entry["start"], entry["end"])


def _gap(first: str, second: str) -> int:
    from datetime import date
    return (date.fromisoformat(second) - date.fromisoformat(first)).days
