"""Signs that a business is picking up speed – the pattern of Micron in 2024:
revenue growing faster and faster, profits returning or outgrowing revenue,
margins widening. From SEC quarterly figures; analyst-based signs follow later."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from quarry.formatting import percent
from quarry.quarters import QuarterFigures, current, growth, quarter_table, year_ago

MIN_GROWTH = 0.15
MIN_ACCELERATION = 0.05  # percentage points faster than the quarter before
MIN_PROFIT_GROWTH = 0.25
MIN_MARGIN_GAIN = 0.03
# Below this quarterly revenue, percentages explode from tiny amounts (early biotech, shells).
MIN_REVENUE = 20_000_000
NEW_WITHIN_DAYS = 7
# Signals that make the score; insider buying counts as well.
UPSWING_KINDS = ["acceleration", "turnaround", "margin", "insider"]
RANKING_MIN_SCORE = 2
HISTORY_DAYS = 183


def upswing_signals(table: list[QuarterFigures], today: date) -> list[dict]:
    """Acceleration, turnaround and margin signals for the latest quarter."""
    fresh = bool(table) and table[-1].filed >= today - timedelta(days=NEW_WITHIN_DAYS)
    return [
        _with_new(_acceleration(table), fresh),
        _with_new(_turnaround(table), fresh),
        _with_new(_margin(table), fresh),
    ]


def revenue_growth_latest(table: list[QuarterFigures]) -> float | None:
    if not table:
        return None
    previous = year_ago(table, table[-1])
    return growth(table[-1].revenue, previous.revenue if previous else None)


def is_newcomer(table: list[QuarterFigures], today: date, score: int) -> bool:
    """Reached the ranking with the latest report: one quarter earlier it would not have."""
    if score < RANKING_MIN_SCORE or len(table) < 2 or table[-1].filed < today - timedelta(days=NEW_WITHIN_DAYS * 2):
        return False
    before = sum(1 for signal in upswing_signals(table[:-1], today) if signal["isActive"])
    now = sum(1 for signal in upswing_signals(table, today) if signal["isActive"])
    return before < now and before < RANKING_MIN_SCORE


def upswing_event(cik: int, filed: date, facts: dict | None) -> dict | None:
    """A feed event when a fresh quarterly report shows signs of an upswing."""
    active = [signal for signal in upswing_signals(current(quarter_table(facts or {}), filed), filed)
              if signal["isActive"]]
    if not active:
        return None
    return {"kind": active[0]["kind"], "cik": cik, "date": filed.isoformat(), "headline": active[0]["headline"],
            "signals": [signal["kind"] for signal in active]}


def _acceleration(table: list[QuarterFigures]) -> dict:
    if len(table) < 2:
        return _signal("acceleration", False, "Keine Vergleichszahlen", "Für einen Vergleich fehlen Quartalszahlen.")
    latest, previous = table[-1], table[-2]
    now = _yoy(table, latest, "revenue")
    before = _yoy(table, previous, "revenue")
    if now is None:
        return _signal("acceleration", False, "Keine Vergleichszahlen", "Für einen Vergleich fehlen Quartalszahlen.")
    if before is None:
        return _signal("acceleration", False, f"Umsatz {percent(now)}", "Zum Quartal davor fehlt der Vorjahresvergleich.")
    headline = f"Umsatz {percent(now)} (Vorquartal {percent(before)})"
    if (latest.revenue or 0) < MIN_REVENUE:
        return _signal("acceleration", False, headline, "Bei so kleinem Umsatz sagen Prozente wenig.")
    active = now >= MIN_GROWTH and now - before >= MIN_ACCELERATION
    detail = ("Der Umsatz wächst gegenüber dem Vorjahr schneller als noch im Quartal davor." if active
              else "Umsatzwachstum gegenüber dem Vorjahresquartal.")
    return _signal("acceleration", active, headline, detail)


def _turnaround(table: list[QuarterFigures]) -> dict:
    incomes = [q.net_income for q in table]
    if len(table) < 2 or incomes[-1] is None:
        return _signal("turnaround", False, "Keine Gewinnzahlen", "Für die letzten Quartale fehlen Gewinnzahlen.")
    if incomes[-1] > 0 and (incomes[-2] or 0) > 0 and any(i is not None and i < 0 for i in incomes[-6:-2]):
        return _signal("turnaround", True, "Gewinn nach Verlusten",
                       "Zwei Quartale in Folge Gewinn, nachdem die Firma zuvor Verluste gemacht hat.")
    profit_growth = _yoy(table, table[-1], "net_income")
    sales_growth = _yoy(table, table[-1], "revenue")
    if incomes[-1] < 0:
        return _signal("turnaround", False, "Verlust im letzten Quartal", "Die Firma schreibt noch rote Zahlen.")
    if profit_growth is None:
        return _signal("turnaround", False, "Gewinn, Vorjahr ohne Gewinn",
                       "Im Vorjahresquartal gab es keinen Gewinn – ein Vergleich in Prozent ist nicht möglich.")
    headline = f"Gewinn {percent(profit_growth)}" + (f" (Umsatz {percent(sales_growth)})" if sales_growth is not None else "")
    active = profit_growth >= MIN_PROFIT_GROWTH and (sales_growth is None or profit_growth > sales_growth)
    detail = ("Der Gewinn wächst schneller als der Umsatz – die Firma verdient an jedem Dollar mehr." if active
              else "Gewinn gegenüber dem Vorjahresquartal.")
    return _signal("turnaround", active, headline, detail)


def _margin(table: list[QuarterFigures]) -> dict:
    if not table:
        return _signal("margin", False, "Keine Margen-Angaben", "Für die letzten Quartale fehlen Margen-Angaben.")
    latest = table[-1]
    previous = year_ago(table, latest)
    for name, now, before in (
        ("Bruttomarge", latest.gross_margin, previous.gross_margin if previous else None),
        ("Operative Marge", latest.operating_margin, previous.operating_margin if previous else None),
    ):
        if now is not None and before is not None and -1 <= now <= 1 and -1 <= before <= 1:
            headline = f"{name} {now * 100:.0f} % (Vorjahr {before * 100:.0f} %)"
            active = now - before >= MIN_MARGIN_GAIN and (latest.revenue or 0) >= MIN_REVENUE
            detail = (f"Von jedem Dollar Umsatz bleiben {now * 100:.0f} Cent statt {before * 100:.0f} Cent vor einem Jahr."
                      if active else f"{name} im Vergleich zum Vorjahresquartal.")
            return _signal("margin", active, headline, detail)
    return _signal("margin", False, "Keine Margen-Angaben", "Für die letzten Quartale fehlen Margen-Angaben.")


def _yoy(table: list[QuarterFigures], quarter: QuarterFigures, field: str) -> float | None:
    previous = year_ago(table, quarter)
    return growth(getattr(quarter, field), getattr(previous, field) if previous else None)


def _with_new(signal: dict, fresh: bool) -> dict:
    signal["isNew"] = signal["isActive"] and fresh
    return signal


def _signal(kind: str, active: bool, headline: str, detail: str) -> dict:
    return {"kind": kind, "isActive": active, "isNew": False, "headline": headline, "detail": detail}


class UpswingStore:
    """The upswing state of every company, kept between runs (profiles rotate), so
    the daily ranking and the sector overview cover all of them – companies
    without any sign included."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.entries: dict[str, dict] = json.loads(self.path.read_text()) if self.path.exists() else {}

    def record(self, company: dict, today: date) -> None:
        """Remembers the company's state and adds its strength history (one point per
        change, half a year) and since when it is in the ranking – to the store and to
        the company itself, so profiles carry it too."""
        upswing = company.get("upswing")
        if not upswing:
            self.entries.pop(str(company["cik"]), None)
            return
        previous = self.entries.get(str(company["cik"])) or {}
        cutoff = (today - timedelta(days=HISTORY_DAYS)).isoformat()
        history = [point for point in previous.get("history", []) if point[0] >= cutoff]
        if not history or history[-1][1] != upswing["score"]:
            history.append([today.isoformat(), upswing["score"]])
        since = (previous.get("since") or today.isoformat()) if upswing["score"] >= RANKING_MIN_SCORE else None
        upswing["history"] = history
        upswing["since"] = since
        self.entries[str(company["cik"])] = {
            "cik": company["cik"], "ticker": company["ticker"], "name": company["name"],
            "exchange": company["exchange"], "sector": company["sector"],
            "score": upswing["score"], "isNew": upswing["isNew"], "revenueGrowth": upswing.get("revenueGrowth"),
            "since": since, "history": history,
            "signals": [{"kind": s["kind"], "headline": s["headline"], "isNew": s["isNew"]}
                        for s in company["signals"] if s["isActive"] and s["kind"] in UPSWING_KINDS],
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.entries, ensure_ascii=False, separators=(",", ":"), sort_keys=True))

    def ranking(self, today: date) -> dict:
        ranked = sorted((e for e in self.entries.values() if e["score"] >= RANKING_MIN_SCORE),
                        key=lambda e: (e["score"], e["isNew"], e.get("revenueGrowth") or 0), reverse=True)
        return {"version": 1, "generated": today.isoformat(), "maxScore": len(UPSWING_KINDS), "companies": ranked}
