"""Orchestration: process new business days, then rebuild the feed."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from quarry.daily_index import index_url, parse_form_index
from quarry.directory import DIRECTORY_URL, index_json, parse_directory
from quarry.facts import revenue_growth
from quarry.feed import FEED_WINDOW_DAYS, build_company
from quarry.form4 import extract_ownership_xml, parse_form4
from quarry.profiles import build_profiles
from quarry.signals import insider_events, momentum_event

ARCHIVES = "https://www.sec.gov/Archives/"
HISTORY_DAYS = 90


def run(
    client,
    today: date,
    data_dir: Path,
    feed_path: Path,
    process_days: int = 7,
    log=print,
    profiles: bool = True,
    profile_limit: int | None = None,
) -> dict:
    events_dir = Path(data_dir) / "events"
    events_dir.mkdir(parents=True, exist_ok=True)

    for offset in range(process_days, 0, -1):
        day = today - timedelta(days=offset)
        target = events_dir / f"{day.isoformat()}.json"
        if day.weekday() >= 5 or target.exists():
            continue
        index = client.get_text(index_url(day), absent_codes=(403, 404))
        if index is None:
            log(f"{day}: kein Index (Feiertag oder noch nicht veröffentlicht)")
            continue
        events = process_day(client, day, index, log)
        target.write_text(json.dumps(events, ensure_ascii=False, indent=1))
        log(f"{day}: {len(events)} Ereignisse")

    feed = build_feed(client, today, events_dir, log)
    feed_path = Path(feed_path)
    feed_path.parent.mkdir(parents=True, exist_ok=True)
    feed_path.write_text(json.dumps(feed, ensure_ascii=False, indent=1))
    log(f"Feed: {len(feed['companies'])} Firmen -> {feed_path}")

    if profiles:
        build_directory(client, today, events_dir, feed_path.parent, {c["cik"] for c in feed["companies"]}, log, profile_limit)
    return feed


def build_directory(client, today: date, events_dir: Path, public_dir: Path, feed_ciks: set[int], log=print,
                    limit: int | None = None) -> None:
    """index.json for search plus one profile per listed company."""
    raw = client.get_json(DIRECTORY_URL)
    if not raw:
        log("Firmenverzeichnis nicht verfügbar – Profile übersprungen")
        return
    entries = parse_directory(raw)
    (public_dir / "index.json").write_text(json.dumps(index_json(entries), ensure_ascii=False, separators=(",", ":")))
    log(f"Index: {len(entries)} Kürzel")
    written = build_profiles(client, entries, load_events(events_dir, today), today, public_dir / "companies",
                             feed_ciks, log, limit)
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


def process_day(client, day: date, index_text: str, log=print) -> list[dict]:
    entries = parse_form_index(index_text, {"4", "10-Q", "10-K"})

    filings = []
    form4_entries = [entry for entry in entries if entry.form == "4"]
    for number, entry in enumerate(form4_entries, start=1):
        if number % 250 == 0:
            log(f"{day}: Form 4 {number}/{len(form4_entries)}")
        xml = extract_ownership_xml(client.get_text(ARCHIVES + entry.path) or "")
        if xml:
            try:
                filings.append(parse_form4(xml))
            except Exception as error:  # malformed filings must not stop the run
                log(f"Form 4 übersprungen ({entry.path}): {error}")
    events = insider_events(filings, day)

    for cik in sorted({entry.cik for entry in entries if entry.form in ("10-Q", "10-K")}):
        facts = client.get_json(_facts_url(cik))
        event = momentum_event(cik, day, revenue_growth(facts) if facts else None)
        if event:
            events.append(event)
    return events


def build_feed(client, today: date, events_dir: Path, log=print) -> dict:
    by_company = load_events(events_dir, today)

    companies = []
    window_start = (today - timedelta(days=FEED_WINDOW_DAYS)).isoformat()
    for cik, events in by_company.items():
        if not any(event["date"] >= window_start for event in events):
            continue
        submissions = client.get_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
        if not submissions:
            continue
        company = build_company(cik, events, submissions, client.get_json(_facts_url(cik)), today)
        if company:
            companies.append(company)

    companies.sort(key=lambda c: (c["importance"], c["trigger"]["date"]), reverse=True)
    return {
        "version": 1,
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "companies": companies,
    }


def _facts_url(cik: int) -> str:
    return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
