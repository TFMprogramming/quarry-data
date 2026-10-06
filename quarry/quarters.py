"""Quarter by quarter: revenue, profit and margins from SEC company facts.

Companies report most quarters on their own, but the fourth fiscal quarter
usually only inside the annual report. It is derived as the year minus the
three quarters before it, so every series is complete."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from quarry.facts import REVENUE_CONCEPTS

QUARTER_DAYS = range(80, 101)
# The latest quarter must be this fresh, or the company has stopped reporting in a way we can read.
MAX_AGE_DAYS = 200
YEAR_DAYS = range(350, 381)
TOLERANCE = timedelta(days=4)
MAX_QUARTERS = 12


@dataclass
class QuarterFigures:
    start: date
    end: date
    filed: date
    revenue: float | None = None
    net_income: float | None = None
    gross_profit: float | None = None
    operating_income: float | None = None

    @property
    def gross_margin(self) -> float | None:
        return _ratio(self.gross_profit, self.revenue)

    @property
    def operating_margin(self) -> float | None:
        return _ratio(self.operating_income, self.revenue)


def quarter_table(facts: dict) -> list[QuarterFigures]:
    """The latest quarters, oldest first."""
    gaap = (facts or {}).get("facts", {}).get("us-gaap", {})
    revenue = _series(gaap, REVENUE_CONCEPTS)
    if not revenue:
        return []
    income = _series(gaap, ["NetIncomeLoss", "ProfitLoss"])
    gross = _series(gaap, ["GrossProfit"])
    cost = _series(gaap, ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"])
    operating = _series(gaap, ["OperatingIncomeLoss"])

    table = []
    for end in sorted(revenue)[-MAX_QUARTERS:]:
        start, value, filed = revenue[end]
        gross_profit = _value(gross, end)
        if gross_profit is None and _value(cost, end) is not None:
            gross_profit = value - _value(cost, end)
        table.append(QuarterFigures(start, end, filed, value, _value(income, end), gross_profit, _value(operating, end)))
    return table


def current(table: list[QuarterFigures], today: date) -> list[QuarterFigures]:
    """The table if its latest quarter is recent, otherwise nothing."""
    if not table or table[-1].end < today - timedelta(days=MAX_AGE_DAYS):
        return []
    return table


def year_ago(table: list[QuarterFigures], quarter: QuarterFigures) -> QuarterFigures | None:
    """The same quarter one year earlier (52/53-week years shift the end date a little)."""
    target = quarter.end - timedelta(days=364)
    candidates = [q for q in table if abs(q.end - target) <= timedelta(days=10)]
    return min(candidates, key=lambda q: abs(q.end - target)) if candidates else None


def growth(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous <= 0:
        return None
    return current / previous - 1


def _series(gaap: dict, concepts: list[str]) -> dict[date, tuple[date, float, date]]:
    """End date -> (start, value, filed) of three-month figures; earlier concepts win."""
    series: dict[date, tuple[date, float, date]] = {}
    for concept in concepts:
        quarters, years = _durations(gaap.get(concept, {}).get("units", {}).get("USD", []))
        for (start, end), (value, filed) in quarters.items():
            if not any(abs(end - known) <= TOLERANCE for known in series):
                series[end] = (start, value, filed)
        for (start, end), (value, filed) in years.items():
            inside = [(s, e, v) for (s, e), (v, _) in quarters.items() if s >= start - TOLERANCE and e <= end + TOLERANCE]
            if len(inside) == 3 and not any(abs(e - end) <= TOLERANCE for _, e, _ in inside):
                fourth_end = end
                if not any(abs(fourth_end - known) <= TOLERANCE for known in series):
                    last_end = max(e for _, e, _ in inside)
                    series[fourth_end] = (last_end + timedelta(days=1), value - sum(v for _, _, v in inside), filed)
    return series


def _durations(entries: list[dict]) -> tuple[dict, dict]:
    """Three-month and twelve-month figures by (start, end): the value of the latest
    filing (corrections win), dated by the first filing (when it became known)."""
    quarters: dict[tuple[date, date], tuple[float, date]] = {}
    years: dict[tuple[date, date], tuple[float, date]] = {}
    latest: dict[tuple[date, date], tuple[date, float]] = {}
    for entry in entries:
        if not entry.get("start"):
            continue
        start, end = date.fromisoformat(entry["start"]), date.fromisoformat(entry["end"])
        filed = date.fromisoformat(entry.get("filed") or entry["end"])
        days = (end - start).days
        bucket = quarters if days in QUARTER_DAYS else years if days in YEAR_DAYS else None
        if bucket is None:
            continue
        known_latest = latest.get((start, end))
        if known_latest is None or filed >= known_latest[0]:
            latest[(start, end)] = (filed, float(entry["val"]))
        known = bucket.get((start, end))
        first = min(known[1], filed) if known else filed
        bucket[(start, end)] = (latest[(start, end)][1], first)
    return quarters, years


def _value(series: dict, end: date) -> float | None:
    for known, (_, value, _) in series.items():
        if abs(known - end) <= TOLERANCE:
            return value
    return None


def _ratio(part: float | None, whole: float | None) -> float | None:
    if part is None or whole is None or whole <= 0:
        return None
    return part / whole
