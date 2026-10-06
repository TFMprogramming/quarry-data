"""One profile per listed company, refreshed in a five-day rotation."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from quarry.directory import DirectoryEntry
from quarry.extras import CompanyExtras
from quarry.feed import build_company

ROTATION_DAYS = 5
# Raise when profiles gain fields: every profile is then rebuilt once.
PROFILE_VERSION = 4


def is_due(cik: int, today: date, exists: bool, feed_ciks: set[int]) -> bool:
    """Missing profiles and feed companies always; everything else once per rotation."""
    return not exists or cik in feed_ciks or cik % ROTATION_DAYS == today.weekday() % ROTATION_DAYS


def build_profiles(
    client,
    entries: list[DirectoryEntry],
    events_by_cik: dict[int, list[dict]],
    today: date,
    out_dir: Path,
    feed_ciks: set[int],
    log=print,
    limit: int | None = None,
    extras: CompanyExtras | None = None,
) -> int:
    """`feed_ciks` are always rebuilt – feed companies and those with new filings."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    extras = extras or CompanyExtras()
    version_file = out_dir / "version.txt"
    outdated = not version_file.exists() or version_file.read_text().strip() != str(PROFILE_VERSION)
    ciks = list(dict.fromkeys(entry.cik for entry in entries))  # unique, in directory order
    due = [cik for cik in ciks
           if outdated or is_due(cik, today, (out_dir / f"{cik}.json").exists(), feed_ciks)]
    log(f"Profile: {len(due)} von {len(ciks)} fällig" + (" (neues Format)" if outdated else ""))

    written = 0
    for number, cik in enumerate(due, start=1):
        if limit is not None and written >= limit:
            break
        if number % 250 == 0:
            log(f"Profile {number}/{len(due)}")
        submissions = client.get_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
        if not submissions:
            continue
        facts = client.get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")
        company = build_company(cik, events_by_cik.get(cik, []), submissions, facts, today, require_recent=False,
                                **extras.for_company(client, cik, submissions, today))
        if company:
            extras.record(company)
            (out_dir / f"{cik}.json").write_text(json.dumps(company, ensure_ascii=False, separators=(",", ":")))
            written += 1
    if limit is None:
        version_file.write_text(str(PROFILE_VERSION))
    return written
