"""Where upswings happen: every sector with its share of companies in an
upswing, typical revenue growth and its members – published daily as
`sectors.json` for the Branchen view and company comparisons."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from statistics import median

from quarry.upswing import RANKING_MIN_SCORE

# Sectors with fewer companies say little; they are grouped as "Weitere".
MIN_COMPANIES = 8
# Not sectors an investor would compare against.
LEFT_OUT = {"Mantelgesellschaften", "Sonstige"}


def sector_overview(entries: dict[str, dict], today: date) -> dict:
    """`entries`: the upswing store – every company with its sector, score and growth."""
    by_sector: dict[str, list[dict]] = {}
    for company in entries.values():
        if company.get("sector") and company["sector"] not in LEFT_OUT:
            by_sector.setdefault(company["sector"], []).append(company)

    sectors, other = [], []
    for name, companies in by_sector.items():
        if len(companies) < MIN_COMPANIES:
            other.extend(companies)
        else:
            sectors.append(_stats(name, companies))
    sectors.sort(key=lambda s: (s["share"], s["upswing"]), reverse=True)
    return {
        "version": 1,
        "generated": today.isoformat(),
        "minScore": RANKING_MIN_SCORE,
        "sectors": sectors,
        "other": _stats("Weitere", other) if other else None,
    }


def _stats(name: str, companies: list[dict]) -> dict:
    upswing = sum(1 for c in companies if c["score"] >= RANKING_MIN_SCORE)
    growths = [c["revenueGrowth"] for c in companies if c.get("revenueGrowth") is not None]
    members = sorted(companies, key=lambda c: (c["score"], c.get("revenueGrowth") or -1), reverse=True)
    return {
        "name": name,
        "companies": len(companies),
        "upswing": upswing,
        "share": round(upswing / len(companies), 3),
        "medianGrowth": round(median(growths), 3) if growths else None,
        "members": [[c["cik"], c["ticker"], c["name"], c["score"],
                     round(c["revenueGrowth"], 3) if c.get("revenueGrowth") is not None else None]
                    for c in members],
    }


class SectorHistory:
    """Daily counts of companies in an upswing per sector, for the change over a week."""

    KEEP_DAYS = 35
    WEEK = 7

    def __init__(self, path: Path):
        self.path = Path(path)
        self.days: dict[str, dict[str, int]] = json.loads(self.path.read_text()) if self.path.exists() else {}

    def update(self, overview: dict, today: date) -> None:
        """Records today's counts and adds each sector's change against a week ago,
        plus the sector of the week (the largest increase), to `overview`."""
        self.days[today.isoformat()] = {s["name"]: s["upswing"] for s in overview["sectors"]}
        cutoff = (today - timedelta(days=self.KEEP_DAYS)).isoformat()
        self.days = {day: counts for day, counts in self.days.items() if day >= cutoff}
        week_ago = (today - timedelta(days=self.WEEK)).isoformat()
        earlier = [day for day in self.days if day <= week_ago]
        before = self.days[max(earlier)] if earlier else None
        for sector in overview["sectors"]:
            sector["change"] = sector["upswing"] - before[sector["name"]] if before and sector["name"] in before else None
        rising = [s for s in overview["sectors"] if (s["change"] or 0) > 0]
        overview["sectorOfTheWeek"] = max(rising, key=lambda s: (s["change"], s["share"]))["name"] if rising else None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.days, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
