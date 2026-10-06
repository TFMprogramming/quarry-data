"""Where upswings happen: every sector with its share of companies in an
upswing, typical revenue growth and its members – published daily as
`sectors.json` for the Branchen view and company comparisons."""
from __future__ import annotations

from datetime import date
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
