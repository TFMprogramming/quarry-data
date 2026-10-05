"""Assemble one feed company in the app's JSON format."""
from __future__ import annotations

from datetime import date, timedelta

from quarry.facts import public_float, quarters, revenue_growth
from quarry.formatting import money, percent
from quarry.signals import ATTENTION_MAX_FLOAT, MOMENTUM_MIN_GROWTH

LISTED_EXCHANGES = {"Nasdaq": "NASDAQ", "NYSE": "NYSE", "NYSE American": "AMEX", "NYSE Arca": "AMEX", "CBOE": "CBOE"}
FEED_WINDOW_DAYS = 7
NEW_WITHIN_DAYS = 2


def build_company(cik: int, events: list[dict], submissions: dict, facts: dict | None, today: date) -> dict | None:
    """`events` are all of the company's events from the last 90 days."""
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
    if not recent:
        return None

    insider = [event for event in events if event["kind"] == "insider"]
    insider_total = sum(event["value"] for event in insider)
    trades = sorted((trade for event in insider for trade in event["trades"]), key=lambda t: t["date"], reverse=True)

    growth = revenue_growth(facts)

    signals = [
        _signal("value", False, "Bald verfügbar", "Die Bewertung kommt mit lizenzierten Kursdaten."),
        _overlooked_signal(floating),
        _insider_signal(insider, insider_total, new_start),
        _trend_signal(growth, any(e["kind"] == "trend" and e["date"] >= new_start for e in events)),
    ]

    trigger_event = max(recent, key=lambda event: (event["date"], event["kind"] == "insider"))
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
        "tradingViewSymbol": f"{LISTED_EXCHANGES[exchange]}:{ticker}",
        "sector": submissions.get("sicDescription") or "Unbekannt",
        "publicFloat": floating,
        "importance": importance,
        "trigger": {"kind": trigger_event["kind"], "headline": _headline(trigger_event), "date": trigger_event["date"]},
        "signals": signals,
        "insiderTrades": trades[:10],
        "financials": [
            {"period": q.period, "revenue": q.revenue, "netIncome": q.net_income} for q in quarters(facts)
        ],
    }


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
    # str.title() would turn "DICK'S" into "Dick'S"; capitalise word by word instead.
    return " ".join(word.capitalize() for word in name.split()) if name.isupper() else name
