"""Turn raw filings into dated events. Thresholds live here."""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from quarry.form4 import InsiderFiling

INSIDER_MIN_VALUE = 25_000
MOMENTUM_MIN_GROWTH = 0.20
ATTENTION_MAX_FLOAT = 2_000_000_000


def insider_events(filings: list[InsiderFiling], filed: date) -> list[dict]:
    """One event per issuer with officer/director purchases of at least INSIDER_MIN_VALUE."""
    by_issuer: dict[int, list[InsiderFiling]] = defaultdict(list)
    for filing in filings:
        if filing.role and filing.purchases and filing.ticker:
            by_issuer[filing.issuer_cik].append(filing)

    events = []
    for cik, issuer_filings in by_issuer.items():
        trades = [
            {
                "name": filing.owner_name,
                "role": filing.role,
                "date": max(p.date for p in filing.purchases).isoformat(),
                "shares": round(sum(p.shares for p in filing.purchases)),
                "value": round(sum(p.value for p in filing.purchases)),
            }
            for filing in issuer_filings
        ]
        total = sum(trade["value"] for trade in trades)
        if total >= INSIDER_MIN_VALUE:
            events.append({
                "kind": "insider",
                "cik": cik,
                "ticker": issuer_filings[0].ticker,
                "date": filed.isoformat(),
                "value": total,
                "trades": trades,
            })
    return events


def momentum_event(cik: int, filed: date, growth: tuple[str, float] | None) -> dict | None:
    if growth is None or growth[1] < MOMENTUM_MIN_GROWTH:
        return None
    period, value = growth
    return {"kind": "trend", "cik": cik, "date": filed.isoformat(), "period": period, "growth": round(value, 4)}
