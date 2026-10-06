"""Analyst data from Eulerpool, for private use only: closing prices, consensus
estimates and earnings surprises. Never published on the public site – the
private repository `quarry-private` runs this module and keeps its output.

    python -m quarry.analyst --data data --out public

Signals: earnings above estimates ("beat"), strong expected growth
("outlook"), estimates being raised ("revisions"). Plus valuations with
Eulerpool closes and a forward P/E."""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from quarry.budget import Budget
from quarry.formatting import percent
from quarry.prices import Close
from quarry.valuation import sector_medians, valuation

EULERPOOL = "https://api.eulerpool.com"
PUBLIC_PAGES = "https://tfmprogramming.github.io/quarry-data/"
PUBLIC_RAW = "https://raw.githubusercontent.com/TFMprogramming/quarry-data/main/"
ROTATION_DAYS = 5
MIN_ANALYSTS = 3
MIN_OUTLOOK_GROWTH = 0.25
MIN_REVISION = 0.05
REVISION_DAYS = 30
MAX_SURPRISES = 8
RANKING_MIN_SCORE = 3
# Keep this many monthly requests in reserve, so a month never runs dry.
MONTHLY_RESERVE = 3000


class EulerpoolClient:
    def __init__(self, api_key: str, max_per_second: float = 5.0, opener=urllib.request.urlopen):
        self.api_key = api_key
        self.min_interval = 1.0 / max_per_second
        self.opener = opener
        self.requests = 0
        self.monthly_remaining: int | None = None
        self._last = 0.0

    def get(self, path: str):
        """Parsed JSON, or None if the resource doesn't exist."""
        for attempt in range(3):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            request = urllib.request.Request(EULERPOOL + path, headers={
                "Authorization": f"Bearer {self.api_key}", "User-Agent": "Quarry (private research app)"})
            try:
                with self.opener(request, timeout=120) as response:
                    self.requests += 1
                    remaining = response.headers.get("x-ratelimit-remaining")
                    if remaining and remaining.isdigit():
                        self.monthly_remaining = int(remaining)
                    return json.loads(response.read() or b"null")
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    return None
                if error.code in (429, 500, 502, 503) and attempt < 2:
                    time.sleep(5 * (attempt + 1))
                    continue
                raise
        return None

    @property
    def has_quota(self) -> bool:
        return self.monthly_remaining is None or self.monthly_remaining > MONTHLY_RESERVE


def closes_from_bulk(rows: list[dict], tickers: set[str]) -> dict[str, Close]:
    closes = {}
    for row in rows:
        for bar in row.get("payload") or []:
            symbol, day, close = bar.get("symbol"), bar.get("date"), bar.get("close")
            if symbol in tickers and day and close:
                try:
                    closes[symbol] = (day, float(close))
                except ValueError:
                    continue
    return closes


def fetch_closes(client: EulerpoolClient, tickers: set[str]) -> dict[str, Close]:
    rows, offset = [], 0
    while True:
        page = client.get(f"/api/1/datasets/eod-bulk?limit=2000&offset={offset}")
        if not page:
            break
        rows.extend(page.get("data") or [])
        offset += 2000
        if offset >= page.get("total", 0):
            break
    return closes_from_bulk(rows, tickers)


def estimate_summary(rows: list[dict] | None, today: date) -> dict | None:
    """Consensus EPS for the next fiscal year against the year just ended."""
    yearly = sorted((r for r in rows or [] if not r.get("quarter") and r.get("epsEstimate") is not None),
                    key=lambda r: r["period"])
    upcoming = [r for r in yearly if r["period"] > today.isoformat()]
    past = [r for r in yearly if r["period"] <= today.isoformat()]
    if not upcoming:
        return None
    next_year = upcoming[0]
    previous = past[-1]["epsEstimate"] if past else None
    growth = round(next_year["epsEstimate"] / previous - 1, 3) if previous and previous > 0 else None
    return {"year": next_year.get("year"), "period": next_year["period"], "eps": next_year["epsEstimate"],
            "analysts": next_year.get("epsAnalysts") or 0, "previousEps": previous, "growth": growth}


def surprises(pit_rows: list[dict] | None) -> list[dict]:
    """Estimate and actual EPS per reported quarter, from the latest snapshot."""
    latest: dict[tuple[str, str], tuple[str, float]] = {}
    for row in _clean(pit_rows):
        key = (row["period"], row["field"])
        try:
            value = float(row["value"])
        except (TypeError, ValueError):
            continue
        if key not in latest or row["as_of_date"] > latest[key][0]:
            latest[key] = (row["as_of_date"], value)
    periods = sorted({period for period, field in latest if field == "eps_actual"})
    result = [{"period": p, "estimate": latest[(p, "eps_estimate")][1], "actual": latest[(p, "eps_actual")][1]}
              for p in periods if (p, "eps_estimate") in latest]
    return result[-MAX_SURPRISES:]


HISTORY_DAYS = 120


def remember(history: list[list] | None, summary: dict | None, today: date) -> list[list]:
    """Our own record of the consensus for the next fiscal year: [day, period, eps]."""
    history = [entry for entry in history or [] if entry[0] >= (today - timedelta(days=HISTORY_DAYS)).isoformat()]
    if summary and summary.get("eps") is not None:
        history = [entry for entry in history if entry[0] != today.isoformat()]
        history.append([today.isoformat(), summary["period"], summary["eps"]])
    return history


def revision(history: list[list] | None, today: date) -> dict | None:
    """How the consensus for the same fiscal year moved over the last 30 days."""
    if not history:
        return None
    day, period, now = history[-1]
    cutoff = (today - timedelta(days=REVISION_DAYS)).isoformat()
    before = [eps for when, same, eps in history if same == period and when <= cutoff]
    if not before or before[-1] == 0:
        return None
    then = before[-1]
    return {"period": period, "now": now, "before": then, "change": round((now - then) / abs(then), 3)}


def _clean(pit_rows: list[dict] | None) -> list[dict]:
    """Periods and dates come with or without a time ("2026-06-30T00:00:00.000+02:00")."""
    return [dict(row, period=str(row["period"])[:10], as_of_date=str(row["as_of_date"])[:10])
            for row in pit_rows or [] if row.get("period") and row.get("as_of_date")]


def _dollars(value: float) -> str:
    return f"{value:.2f}".replace(".", ",") + " $"


def analyst_signals(summary: dict | None, quarters: list[dict], moved: dict | None) -> list[dict]:
    return [_beat(quarters), _outlook(summary), _revisions(moved)]


def _beat(quarters: list[dict]) -> dict:
    recent = quarters[-4:]
    if len(recent) < 4:
        return _signal("beat", False, "Zu wenige Quartale mit Schätzung", "Für einen Vergleich fehlen Schätzungen.")
    beats = sum(1 for q in recent if q["actual"] > q["estimate"])
    active = beats >= 3 and recent[-1]["actual"] > recent[-1]["estimate"]
    last = recent[-1]
    detail = f"Zuletzt {_dollars(last['actual'])} Gewinn je Aktie bei erwarteten {_dollars(last['estimate'])}."
    return _signal("beat", active, f"{beats} von 4 Quartalen über der Schätzung", detail)


def _outlook(summary: dict | None) -> dict:
    if not summary:
        return _signal("outlook", False, "Keine Schätzung", "Für das nächste Geschäftsjahr liegt keine Analystenschätzung vor.")
    analysts = summary["analysts"]
    who = "1 Analyst" if analysts == 1 else f"{analysts} Analysten"
    growth = summary.get("growth")
    if growth is None:
        return _signal("outlook", False, f"Schätzung von {who}", "Kein Gewinn im Vorjahr – ein Vergleich in Prozent ist nicht möglich.")
    headline = f"Gewinn je Aktie {percent(growth)} erwartet ({who})"
    active = growth >= MIN_OUTLOOK_GROWTH and analysts >= MIN_ANALYSTS
    detail = (f"Konsens für das Geschäftsjahr {summary['year']}." +
              ("" if analysts >= MIN_ANALYSTS else " Zu wenige Analysten für ein belastbares Bild."))
    return _signal("outlook", active, headline, detail)


def _revisions(moved: dict | None) -> dict:
    if not moved:
        return _signal("revisions", False, "Verlauf wird aufgezeichnet",
                       "Quarry zeichnet die Schätzungen selbst auf – nach 30 Tagen lässt sich vergleichen.")
    headline = f"Schätzung {percent(moved['change'])} in 30 Tagen"
    active = moved["change"] >= MIN_REVISION
    detail = "Analysten haben ihre Gewinnerwartung für das Geschäftsjahr " + (
        "angehoben." if moved["change"] > 0 else "gesenkt." if moved["change"] < 0 else "nicht verändert.")
    return _signal("revisions", active, headline, detail)


def _signal(kind: str, active: bool, headline: str, detail: str) -> dict:
    return {"kind": kind, "isActive": active, "isNew": False, "headline": headline, "detail": detail}


class AnalystStore:
    """Estimates and surprises per company, refreshed in a rotation."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.entries: dict[str, dict] = json.loads(self.path.read_text()) if self.path.exists() else {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.entries, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


def company_output(cik: str, entry: dict | None, basis: dict | None, closes: dict[str, Close],
                   medians: dict[str, dict]) -> dict | None:
    """Everything the app shows for one company from the private data."""
    output = {}
    valued = valuation(basis, closes)
    summary = (entry or {}).get("summary")
    if valued:
        sector = medians.get(basis["sector"], {})
        valued.update({"sectorPe": sector.get("pe"), "sectorPs": sector.get("ps")})
        if summary and summary["eps"] and summary["eps"] > 0:
            valued.update({"forwardPe": round(valued["price"] / summary["eps"], 1), "forwardYear": summary["year"],
                           "forwardAnalysts": summary["analysts"]})
        output["valuation"] = valued
    if entry:
        output["estimates"] = summary
        output["surprises"] = entry.get("surprises", [])
        output["signals"] = analyst_signals(summary, entry.get("surprises", []), entry.get("revision"))
    return output or None


def combined_ranking(public: dict[str, dict], companies: dict[str, dict], directory: dict[str, dict],
                     fundamentals: dict[str, dict], today: date) -> dict:
    """The public upswing state plus the analyst signals, out of seven."""
    ranked = []
    for cik in set(public) | {cik for cik, data in companies.items() if data.get("signals")}:
        base = public.get(cik)
        if base is None:
            listing = directory.get(cik)
            if not listing:
                continue
            base = {"cik": int(cik), "ticker": listing["ticker"], "name": listing["name"],
                    "exchange": listing["exchange"], "sector": (fundamentals.get(cik) or {}).get("sector", ""),
                    "score": 0, "isNew": False, "revenueGrowth": None, "signals": []}
        extra = [s for s in (companies.get(cik) or {}).get("signals", []) if s["isActive"]]
        entry = dict(base, score=base["score"] + len(extra),
                     signals=base["signals"] + [{"kind": s["kind"], "headline": s["headline"], "isNew": False}
                                                for s in extra])
        if entry["score"] >= RANKING_MIN_SCORE:
            ranked.append(entry)
    ranked.sort(key=lambda e: (e["score"], e["isNew"], e.get("revenueGrowth") or 0), reverse=True)
    return {"version": 1, "generated": today.isoformat(), "maxScore": 7, "companies": ranked}


def run(client: EulerpoolClient, today: date, data_dir: Path, out_dir: Path, public: dict, budget: Budget,
        log=print) -> None:
    """`public` holds the public pipeline's index rows, fundamentals and upswing store."""
    directory: dict[str, dict] = {}
    for cik, ticker, name, exchange in public["index"]:
        directory.setdefault(str(cik), {"ticker": ticker, "name": name, "exchange": exchange})
    tickers = {listing["ticker"] for listing in directory.values()}

    closes = fetch_closes(client, tickers)
    log(f"Schlusskurse: {len(closes)} Kürzel")

    store = AnalystStore(Path(data_dir) / "analyst.json")
    upswing = public["upswing"]
    due = [cik for cik in directory
           if cik in upswing or cik not in store.entries or int(cik) % ROTATION_DAYS == today.weekday() % ROTATION_DAYS]
    due.sort(key=lambda cik: (cik not in upswing, cik in store.entries))  # ranking companies and new ones first
    log(f"Schätzungen: {len(due)} von {len(directory)} fällig")
    for cik in due:
        if not budget.allows(2) or not client.has_quota:
            log(f"Budget erreicht nach {client.requests} Abrufen")
            break
        ticker = directory[cik]["ticker"]
        budget.spend()
        estimates = client.get(f"/api/1/equity/estimates/{ticker}") or []
        summary = estimate_summary(estimates, today)
        history = remember((store.entries.get(cik) or {}).get("history"), summary, today)
        entry = {"ticker": ticker, "fetched": today.isoformat(), "summary": summary, "surprises": [],
                 "history": history, "revision": revision(history, today)}
        if estimates:  # without analysts there are no surprises either
            budget.spend()
            entry["surprises"] = surprises(client.get(f"/api/1/equity/pit/estimates/{ticker}?limit=500") or [])
        store.entries[cik] = entry
    store.save()

    fundamentals = public["fundamentals"]
    medians = sector_medians(fundamentals, closes)
    companies = {}
    for cik in directory:
        output = company_output(cik, store.entries.get(cik), fundamentals.get(cik), closes, medians)
        if output:
            companies[cik] = output
    days = [day for day, _ in closes.values()]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "analyst.json").write_text(json.dumps(
        {"version": 1, "generated": today.isoformat(), "pricesDate": max(days) if days else None,
         "sectors": medians, "companies": companies}, ensure_ascii=False, separators=(",", ":")))
    ranking = combined_ranking(upswing, companies, directory, fundamentals, today)
    (out_dir / "ranking.json").write_text(json.dumps(ranking, ensure_ascii=False, separators=(",", ":")))
    log(f"Analysten-Daten: {len(companies)} Firmen, Rangliste {len(ranking['companies'])}, "
        f"{client.requests} Abrufe, Monatsrest {client.monthly_remaining}")


def _load_public() -> dict:
    def get(url):
        request = urllib.request.Request(url, headers={"User-Agent": "Quarry"})
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read())
    return {"index": get(PUBLIC_PAGES + "index.json")["companies"],
            "fundamentals": get(PUBLIC_RAW + "data/fundamentals.json"),
            "upswing": get(PUBLIC_RAW + "data/upswing.json")}


def main() -> None:
    parser = argparse.ArgumentParser(description="Quarry analyst data (private)")
    parser.add_argument("--data", default="data")
    parser.add_argument("--out", default="public")
    parser.add_argument("--budget", type=int, default=4000, help="max Eulerpool requests per run")
    args = parser.parse_args()
    key = os.environ.get("EULERPOOL_API_KEY")
    if not key:
        raise SystemExit("EULERPOOL_API_KEY fehlt")
    run(EulerpoolClient(key), date.today(), Path(args.data), Path(args.out), _load_public(), Budget(args.budget))


if __name__ == "__main__":
    main()
