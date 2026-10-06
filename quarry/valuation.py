"""Valuation from our own numbers: market value = closing price × shares
outstanding (SEC cover page); P/E = market value ÷ net income of the last
twelve months; P/S = market value ÷ revenue of the last twelve months.

Each company is compared with the median of its sector. Sector medians use
every company whose figures we have seen (`data/fundamentals.json`)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from statistics import median

from quarry.facts import REVENUE_CONCEPTS, _shares, _trailing_year, quarters
from quarry.prices import Close, close_for

MIN_PEERS = 8
MAX_PE = 1000  # above this the "P/E" says nothing any more
# Share classes of one company trade within this ratio (GOOGL/GOOG), unlike BRK-A/BRK-B.
CLASS_PRICE_RATIO = 1.25
FOREIGN_FORMS = {"20-F", "40-F", "20-F/A", "40-F/A"}
LISTED = {"Nasdaq", "NYSE", "NYSE American", "NYSE Arca", "CBOE"}


def basis(facts: dict, submissions: dict, sector: str) -> dict | None:
    """The SEC figures a valuation needs, or None if they are missing or not comparable."""
    forms = set(submissions.get("filings", {}).get("recent", {}).get("form", []))
    if forms & FOREIGN_FORMS:
        # Foreign filers count ordinary shares while the listed ticker is often an ADR.
        return None
    gaap = (facts or {}).get("facts", {}).get("us-gaap", {})
    shares, _ = _shares(facts or {})
    tickers = [ticker.upper() for ticker, exchange in zip(submissions.get("tickers", []), submissions.get("exchanges", []))
               if ticker and exchange in LISTED]
    if not shares or not tickers:
        return None
    revenue = next((value for value in (_trailing_year(gaap, concept) for concept in REVENUE_CONCEPTS)
                    if value is not None), None)
    latest = next((q for q in reversed(quarters(facts or {})) if q.net_income is not None), None)
    return {"tickers": tickers, "sector": sector, "netIncome": _trailing_year(gaap, "NetIncomeLoss"),
            "revenue": revenue, "shares": shares,
            "quarterIncome": latest.net_income if latest else None, "quarter": latest.period if latest else None}


def valuation(company: dict | None, closes: dict[str, Close]) -> dict | None:
    if not company:
        return None
    prices = [close for close in (close_for(ticker, closes) for ticker in company["tickers"]) if close]
    if not prices:
        return None
    values = [price for _, price in prices]
    if max(values) / min(values) > CLASS_PRICE_RATIO:
        return None  # share classes with different prices: the share count can't be split up
    day, price = prices[0]
    market_cap = price * company["shares"]
    income, revenue = company.get("netIncome"), company.get("revenue")
    pe = market_cap / income if income and income > 0 else None
    # The latest quarter's profit as if it held for a year: where the P/E is heading.
    quarter = company.get("quarterIncome")
    run_rate = market_cap / (4 * quarter) if quarter and quarter > 0 else None
    return {
        "date": day,
        "price": price,
        "marketCap": round(market_cap),
        "pe": round(pe, 1) if pe is not None and pe <= MAX_PE else None,
        "ps": round(market_cap / revenue, 2) if revenue and revenue > 0 else None,
        "peRunRate": round(run_rate, 1) if run_rate is not None and run_rate <= MAX_PE else None,
        "quarter": company.get("quarter") if run_rate is not None else None,
    }


def sector_medians(bases: dict[str, dict], closes: dict[str, Close]) -> dict[str, dict]:
    by_sector: dict[str, list[dict]] = {}
    for company in bases.values():
        value = valuation(company, closes)
        if value:
            by_sector.setdefault(company["sector"], []).append(value)
    medians = {}
    for sector, values in by_sector.items():
        pes = [v["pe"] for v in values if v["pe"] is not None]
        ps = [v["ps"] for v in values if v["ps"] is not None]
        if len(pes) >= MIN_PEERS:
            medians[sector] = {"pe": round(median(pes), 1), "ps": round(median(ps), 2) if ps else None,
                               "count": len(pes)}
    return medians


class FundamentalsStore:
    """Valuation bases by CIK, kept between runs so every sector has its peers."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.entries: dict[str, dict] = json.loads(self.path.read_text()) if self.path.exists() else {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.entries, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


class ValuationContext:
    """What building a company needs to value it: today's closes and the sector medians."""

    def __init__(self, closes: dict[str, Close], medians: dict[str, dict], store: FundamentalsStore | None = None):
        self.closes = closes
        self.medians = medians
        self.store = store

    def value(self, cik: int, company: dict | None) -> dict | None:
        if self.store is not None:
            if company:
                self.store.entries[str(cik)] = company
            else:
                self.store.entries.pop(str(cik), None)
        result = valuation(company, self.closes)
        if result is None:
            return None
        sector = self.medians.get(company["sector"], {})
        result["sectorPe"] = sector.get("pe")
        result["sectorPs"] = sector.get("ps")
        return result


def valuations_json(store: FundamentalsStore, closes: dict[str, Close], today: date) -> dict:
    """Every valued company as [price, market cap, P/E, P/S, run-rate P/E], plus the sector medians –
    published daily, so the app always shows fresh numbers."""
    companies = {}
    for cik, company in store.entries.items():
        value = valuation(company, closes)
        if value:
            companies[cik] = [value["price"], value["marketCap"], value["pe"], value["ps"], value["peRunRate"]]
    days = [day for day, _ in closes.values()]
    return {
        "version": 1,
        "date": max(days) if days else None,
        "generated": today.isoformat(),
        "sectors": sector_medians(store.entries, closes),
        "companies": companies,
    }
