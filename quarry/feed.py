"""Assemble one feed company in the app's JSON format."""
from __future__ import annotations

from datetime import date, timedelta

from quarry.checks import health_checks
from quarry.directory import display_name
from quarry.facts import balance, public_float, quarters, revenue_growth
from quarry.formatting import money, percent
from quarry.sectors import german_sector
from quarry.insiders import insider_profile
from quarry.signals import ATTENTION_MAX_FLOAT, MOMENTUM_MIN_GROWTH
from quarry.timeline import timeline
from quarry.valuation import ValuationContext, basis

LISTED_EXCHANGES = {"Nasdaq": "NASDAQ", "NYSE": "NYSE", "NYSE American": "AMEX", "NYSE Arca": "AMEX", "CBOE": "CBOE"}
FEED_WINDOW_DAYS = 7
NEW_WITHIN_DAYS = 2


def build_company(
    cik: int,
    events: list[dict],
    submissions: dict,
    facts: dict | None,
    today: date,
    require_recent: bool = True,
    insider_records: list[dict] | None = None,
    insider_since: date | None = None,
    holders: list[dict] | None = None,
    holder_filings: dict[str, dict] | None = None,
    valuation_context: ValuationContext | None = None,
) -> dict | None:
    """`events` are all of the company's events from the last 90 days.
    Feed entries need a recent event; profiles (`require_recent=False`) don't and
    then carry no trigger.

    `insider_records` is the company's insider history, complete since
    `insider_since`; `holders` its large shareholders and `holder_filings` the
    parsed 13D/G filings by accession, to name holders in the timeline.
    `valuation_context` brings closing prices and sector medians."""
    listing = _listing(submissions)
    if listing is None:
        return None
    ticker, exchange = listing
    facts = facts or {}

    floating = public_float(facts)
    events = [event for event in events if _is_plausible(event, floating)]

    window_start = (today - timedelta(days=FEED_WINDOW_DAYS)).isoformat()
    new_start = (today - timedelta(days=NEW_WITHIN_DAYS)).isoformat()
    recent = [event for event in events if event["date"] >= window_start]
    if not recent and require_recent:
        return None

    insider = [event for event in events if event["kind"] == "insider"]
    insider_total = sum(event["value"] for event in insider)
    trades = sorted((trade for event in insider for trade in event["trades"]), key=lambda t: t["date"], reverse=True)

    growth = revenue_growth(facts)
    sector = german_sector(submissions.get("sic"))
    valued = valuation_context.value(cik, basis(facts, submissions, sector)) if valuation_context else None
    figures = balance(facts)
    filings = timeline(cik, submissions, today, holder_filings or {})
    if insider_since is not None:
        insider_summary, insider_transactions = insider_profile(insider_records or [], today, insider_since, floating)
    else:
        insider_summary, insider_transactions = None, []

    signals = [
        _value_signal(valued, sector),
        _overlooked_signal(floating),
        _insider_signal(insider, insider_total, new_start),
        _trend_signal(growth, any(e["kind"] == "trend" and e["date"] >= new_start for e in events)),
    ]

    trigger_event = max(recent, key=lambda event: (event["date"], event["kind"] == "insider")) if recent else None
    importance = sum(1 for s in signals if s["isActive"]) + 0.5 * sum(1 for s in signals if s["isActive"] and s["isNew"])
    if insider_total >= 1_000_000:
        importance += 1
    elif insider_total >= 250_000:
        importance += 0.5

    return {
        "cik": cik,
        "ticker": ticker,
        "name": _display_name(submissions.get("name", ticker)),
        "exchange": exchange,
        # SEC writes share classes as "BRK-B", TradingView as "BRK.B".
        "tradingViewSymbol": f"{LISTED_EXCHANGES[exchange]}:{ticker.replace('-', '.')}",
        "sector": sector,
        "industry": submissions.get("sicDescription") or None,
        "publicFloat": floating,
        "importance": importance,
        "trigger": {"kind": trigger_event["kind"], "headline": _headline(trigger_event), "date": trigger_event["date"]}
        if trigger_event else None,
        "signals": signals,
        "insiderTrades": trades[:10],
        "financials": [
            {"period": q.period, "revenue": q.revenue, "netIncome": q.net_income} for q in quarters(facts)
        ],
        "valuation": valued,
        "about": _about(submissions),
        "insiderSummary": insider_summary,
        "insiderTransactions": insider_transactions,
        "holders": holders,  # None: not (completely) known yet
        "events": filings,
        "balance": figures,
        "checks": health_checks(quarters(facts), figures, filings, financial=_is_financial(submissions)),
    }


def _is_financial(submissions: dict) -> bool:
    """Banks, insurers, investment funds and other finance (SIC 6000–6799)."""
    sic = str(submissions.get("sic") or "")
    return sic.isdigit() and 6000 <= int(sic) <= 6799


def _about(submissions: dict) -> dict:
    address = submissions.get("addresses", {}).get("business") or {}
    city = display_name(address.get("city") or "")
    region = address.get("stateOrCountryDescription") if address.get("isForeignLocation") else address.get("stateOrCountry")
    about = {}
    if city:
        about["location"] = f"{city}, {region}" if region else city
    fiscal_end = submissions.get("fiscalYearEnd") or ""
    if len(fiscal_end) == 4 and fiscal_end[:2].isdigit() and 1 <= int(fiscal_end[:2]) <= 12:
        about["fiscalYearEndMonth"] = int(fiscal_end[:2])
    return about


def _is_plausible(event: dict, floating: float | None) -> bool:
    """Filers occasionally misreport prices. A purchase bigger than the whole
    public float cannot be an ordinary open-market buy."""
    return event["kind"] != "insider" or floating is None or event["value"] <= floating


def _listing(submissions: dict) -> tuple[str, str] | None:
    for ticker, exchange in zip(submissions.get("tickers", []), submissions.get("exchanges", [])):
        if exchange in LISTED_EXCHANGES and ticker:
            return ticker.upper(), exchange
    return None


def _headline(event: dict) -> str:
    if event["kind"] == "insider":
        buyers = {trade["name"] for trade in event["trades"]}
        if len(buyers) == 1:
            return f"{event['trades'][0]['role']} kaufte für {money(event['value'])}"
        return f"{len(buyers)} Insider kauften für {money(event['value'])}"
    return f"Umsatz {percent(event['growth'])} ggü. Vorjahresquartal"


def _signal(kind: str, active: bool, headline: str, detail: str, new: bool = False) -> dict:
    return {"kind": kind, "isActive": active, "isNew": active and new, "headline": headline, "detail": detail}


VALUE_DISCOUNT = 0.6  # "günstig": P/E at most 60 % of the sector median


def _value_signal(valued: dict | None, sector: str) -> dict:
    if valued is None:
        return _signal("value", False, "Keine Kursdaten", "Für eine Bewertung fehlen Schlusskurs oder Aktienzahl.")
    pe, sector_pe = valued["pe"], valued.get("sectorPe")
    if pe is None:
        return _signal("value", False, "Kein KGV",
                       "Ohne Gewinn in den letzten zwölf Monaten lässt sich kein KGV berechnen.")
    if not sector_pe:
        return _signal("value", False, f"KGV {_number(pe)}",
                       f"Zu wenige vergleichbare Firmen in der Branche {sector} für einen Vergleich.")
    headline = f"KGV {_number(pe)} · Branche {_number(sector_pe)}"
    detail = (f"Für 1 $ Jahresgewinn zahlt man an der Börse {_number(pe)} $, in der Branche {sector} "
              f"im Mittel {_number(sector_pe)} $.")
    if pe <= VALUE_DISCOUNT * sector_pe:
        return _signal("value", True, headline,
                       detail + " Ein niedriges KGV kann auch heißen, dass der Markt sinkende Gewinne erwartet.")
    return _signal("value", False, headline, detail)


def _number(value: float) -> str:
    return f"{value:.0f}" if value >= 10 or value == int(value) else f"{value:.1f}".replace(".", ",")


def _overlooked_signal(floating: float | None) -> dict:
    if floating is None:
        return _signal("overlooked", False, "Kein Signal", "Keine Angabe zum Streubesitz.")
    if floating < ATTENTION_MAX_FLOAT:
        return _signal("overlooked", True, f"Streubesitz {money(floating)}",
                       "Kleine Firma – solche Werte verfolgen Analysten und Fonds seltener.")
    return _signal("overlooked", False, "Kein Signal", f"Streubesitz {money(floating)} – keine kleine Firma.")


def _insider_signal(events: list[dict], total: float, new_start: str) -> dict:
    if not events:
        return _signal("insider", False, "Kein Signal", "Keine Käufe von Vorständen oder Direktoren in den letzten 90 Tagen.")
    count = sum(len(event["trades"]) for event in events)
    return _signal(
        "insider", True,
        f"{count} {'Kauf' if count == 1 else 'Käufe'} · {money(total)}",
        f"Vorstände oder Direktoren haben in den letzten 90 Tagen für {money(total)} eigene Aktien gekauft.",
        new=any(event["date"] >= new_start for event in events),
    )


def _trend_signal(growth: tuple[str, float] | None, is_new: bool) -> dict:
    if growth is None:
        return _signal("trend", False, "Kein Signal", "Keine vergleichbaren Quartalszahlen verfügbar.")
    period, value = growth
    if value >= MOMENTUM_MIN_GROWTH:
        return _signal("trend", True, f"Umsatz {percent(value)}",
                       f"Umsatz im Quartal {period} gegenüber dem Vorjahresquartal.", new=is_new)
    return _signal("trend", False, "Kein Signal", f"Umsatz {percent(value)} im Quartal {period} – unter +20 %.")


def _display_name(name: str) -> str:
    return display_name(name)
