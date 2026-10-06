"""Orchestration: process new business days, then rebuild the feed."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from quarry.budget import Budget
from quarry.daily_index import index_url, parse_form_index
from quarry.directory import DIRECTORY_URL, index_json, parse_directory
from quarry.extras import CompanyExtras
from quarry.feed import FEED_WINDOW_DAYS, build_company
from quarry.holders import HolderCache
from quarry.insiders import HISTORY_DAYS as INSIDER_HISTORY_DAYS
from quarry.insiders import InsiderStore, backfill, fetch_filings, records_from_filing
from quarry.profiles import build_profiles
from quarry.prices import fetch_closes
from quarry.signals import insider_events
from quarry.upswing import UpswingStore, upswing_event
from quarry.valuation import FundamentalsStore, ValuationContext, sector_medians, valuations_json

HISTORY_DAYS = 90
# Forms that mean a company's profile is worth rebuilding today.
FRESH_FORMS = {"4", "10-Q", "10-K", "8-K", "SCHEDULE 13D", "SCHEDULE 13D/A", "SCHEDULE 13G"}


def run(
    client,
    today: date,
    data_dir: Path,
    feed_path: Path,
    process_days: int = 7,
    log=print,
    profiles: bool = True,
    profile_limit: int | None = None,
    insider_budget: int = 15_000,
    holder_budget: int = 10_000,
    databento_key: str | None = None,
    closes: dict | None = None,
) -> dict:
    """`databento_key` enables closing prices and with them valuations;
    tests pass `closes` directly."""
    events_dir = Path(data_dir) / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    store = InsiderStore(Path(data_dir) / "insiders")
    fresh_ciks: set[int] = set()

    for offset in range(process_days, 0, -1):
        day = today - timedelta(days=offset)
        target = events_dir / f"{day.isoformat()}.json"
        if day.weekday() >= 5 or target.exists():
            continue
        index = client.get_text(index_url(day), absent_codes=(403, 404))
        if index is None:
            log(f"{day}: kein Index (Feiertag oder noch nicht veröffentlicht)")
            continue
        events = process_day(client, day, index, log, store)
        target.write_text(json.dumps(events, ensure_ascii=False, indent=1))
        fresh_ciks |= {entry.cik for entry in parse_form_index(index, FRESH_FORMS)}
        fresh_ciks |= {record["cik"] for record in json.loads((store.directory / f"{day}.json").read_text())}
        log(f"{day}: {len(events)} Ereignisse")

    backfill(client, store, today, Budget(insider_budget), log)
    holder_cache = HolderCache(Path(data_dir) / "holders.json")
    fundamentals = FundamentalsStore(Path(data_dir) / "fundamentals.json")
    if closes is None:
        closes = fetch_closes(databento_key, today, log=log) if databento_key else {}
        if not databento_key:
            log("Kein Databento-Schlüssel – Bewertung übersprungen")
    extras = CompanyExtras(
        insiders=store.load(today - timedelta(days=INSIDER_HISTORY_DAYS + 7)),
        insider_since=None if store.is_empty() else store.coverage_start(today),
        holder_cache=holder_cache,
        holder_budget=Budget(holder_budget),
        valuation=ValuationContext(closes, sector_medians(fundamentals.entries, closes), fundamentals),
        upswing=UpswingStore(Path(data_dir) / "upswing.json"),
    )

    feed = build_feed(client, today, events_dir, log, extras)
    holder_cache.save()
    feed_path = Path(feed_path)
    feed_path.parent.mkdir(parents=True, exist_ok=True)
    feed_path.write_text(json.dumps(feed, ensure_ascii=False, indent=1))
    log(f"Feed: {len(feed['companies'])} Firmen -> {feed_path}")

    if profiles:
        build_directory(client, today, events_dir, feed_path.parent, {c["cik"] for c in feed["companies"]} | fresh_ciks,
                        log, profile_limit, extras)
        holder_cache.save()
    fundamentals.save()
    extras.upswing.save()
    ranking = extras.upswing.ranking(today)
    (feed_path.parent / "upswing.json").write_text(json.dumps(ranking, ensure_ascii=False, separators=(",", ":")))
    log(f"Aufschwung: {len(ranking['companies'])} Firmen in der Rangliste")
    if closes:
        valuations = valuations_json(fundamentals, closes, today)
        (feed_path.parent / "valuations.json").write_text(json.dumps(valuations, ensure_ascii=False, separators=(",", ":")))
        log(f"Bewertungen: {len(valuations['companies'])} Firmen, {len(valuations['sectors'])} Branchen")
    return feed


def build_directory(client, today: date, events_dir: Path, public_dir: Path, feed_ciks: set[int], log=print,
                    limit: int | None = None, extras: CompanyExtras | None = None) -> None:
    """index.json for search plus one profile per listed company."""
    raw = client.get_json(DIRECTORY_URL)
    if not raw:
        log("Firmenverzeichnis nicht verfügbar – Profile übersprungen")
        return
    entries = parse_directory(raw)
    (public_dir / "index.json").write_text(json.dumps(index_json(entries), ensure_ascii=False, separators=(",", ":")))
    log(f"Index: {len(entries)} Kürzel")
    written = build_profiles(client, entries, load_events(events_dir, today), today, public_dir / "companies",
                             feed_ciks, log, limit, extras)
    log(f"Profile geschrieben: {written}")


def load_events(events_dir: Path, today: date) -> dict[int, list[dict]]:
    """All events of the last HISTORY_DAYS days, grouped by company."""
    history_start = (today - timedelta(days=HISTORY_DAYS)).isoformat()
    by_company: dict[int, list[dict]] = defaultdict(list)
    for path in sorted(Path(events_dir).glob("*.json")):
        if path.stem >= history_start:
            for event in json.loads(path.read_text()):
                by_company[event["cik"]].append(event)
    return by_company


def process_day(client, day: date, index_text: str, log=print, store: InsiderStore | None = None) -> list[dict]:
    """The day's signal events; with a `store`, also its insider transactions."""
    entries = parse_form_index(index_text, {"4", "10-Q", "10-K"})

    parsed = fetch_filings(client, [entry for entry in entries if entry.form == "4"], log)
    events = insider_events([filing for _, filing in parsed], day)
    if store is not None:
        store.write(day.isoformat(), [record for accession, filing in parsed
                                      for record in records_from_filing(filing, accession)])

    for cik in sorted({entry.cik for entry in entries if entry.form in ("10-Q", "10-K")}):
        facts = client.get_json(_facts_url(cik))
        event = upswing_event(cik, day, facts)
        if event:
            events.append(event)
    return events


def build_feed(client, today: date, events_dir: Path, log=print, extras: CompanyExtras | None = None) -> dict:
    by_company = load_events(events_dir, today)
    extras = extras or CompanyExtras()

    companies = []
    window_start = (today - timedelta(days=FEED_WINDOW_DAYS)).isoformat()
    for cik, events in by_company.items():
        if not any(event["date"] >= window_start for event in events):
            continue
        submissions = client.get_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
        if not submissions:
            continue
        company = build_company(cik, events, submissions, client.get_json(_facts_url(cik)), today,
                                **extras.for_company(client, cik, submissions, today))
        if company:
            extras.record(company)
            companies.append(company)

    companies.sort(key=lambda c: (c["importance"], c["trigger"]["date"]), reverse=True)
    return {
        "version": 1,
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "companies": companies,
    }


def _facts_url(cik: int) -> str:
    return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
