"""A year of insider purchases and sales for every company.

Stored as one file per filing day in `data/insiders/`. Whole quarters come
from the SEC's quarterly Form 3/4/5 data sets (one download instead of tens
of thousands of filings); days after the latest data set are read filing by
filing, newest first, within a request budget."""
from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from quarry.budget import Budget
from quarry.daily_index import index_url, parse_form_index
from quarry.form4 import (InsiderFiling, _person_name, display_role, extract_ownership_xml, parse_form4,
                          role_for, tidy_role)

ARCHIVES = "https://www.sec.gov/Archives/"
DATASETS_PAGE = "https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets"
HISTORY_DAYS = 365
# Indexes of the last few days may simply not be out yet; older missing ones are holidays.
INDEX_GRACE_DAYS = 3
MAX_TRANSACTIONS = 50
MAX_PEOPLE = 5
DATASET_LINK = re.compile(r'href="([^"]*/(\d{4}q[1-4])_form345\.zip)"')


def records_from_filing(filing: InsiderFiling, accession: str) -> list[dict]:
    """One record per filing, kind and day – sales are often split into many price tranches."""
    grouped: dict[tuple[str, str], list] = defaultdict(list)
    for transaction in filing.transactions:
        grouped[(transaction.code, transaction.date.isoformat())].append(transaction)
    return [
        _record(filing.issuer_cik, accession, filing.owner_name, filing.display_role, code, day,
                [(t.shares, t.price, t.shares_after) for t in group], group[0].planned)
        for (code, day), group in grouped.items()
    ]


def _record(cik, accession, name, role, code, day, tranches, planned) -> dict:
    shares = sum(shares for shares, _, _ in tranches)
    value = sum(shares * price for shares, price, _ in tranches)
    return {
        "cik": cik, "acc": accession, "name": name, "role": role, "code": code, "date": day,
        "shares": round(shares), "price": round(value / shares, 4), "after": _whole(tranches[-1][2]),
        "planned": planned,
    }


def parse_dataset(archive_bytes: bytes) -> dict[str, list[dict]]:
    """Filing day -> records, from one quarterly data set. Amendments are skipped:
    they repeat the original filing."""
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        submissions = {
            row["ACCESSION_NUMBER"]: row for row in _tsv(archive, "SUBMISSION.tsv") if row["DOCUMENT_TYPE"] == "4"
        }
        owners: dict[str, dict] = {}
        for row in _tsv(archive, "REPORTINGOWNER.tsv"):
            owners.setdefault(row["ACCESSION_NUMBER"], row)  # the first owner, like in the XML
        tranches: dict[tuple, list] = defaultdict(list)
        for row in _tsv(archive, "NONDERIV_TRANS.tsv"):
            code, direction = row["TRANS_CODE"], row["TRANS_ACQUIRED_DISP_CD"]
            shares, price = _number(row["TRANS_SHARES"]), _number(row["TRANS_PRICEPERSHARE"])
            if row["ACCESSION_NUMBER"] in submissions and (code, direction) in (("P", "A"), ("S", "D")) \
                    and shares and price and shares > 0 and price > 0:
                key = (row["ACCESSION_NUMBER"], code, _dataset_day(row["TRANS_DATE"]))
                tranches[key].append((shares, price, _number(row["SHRS_OWND_FOLWNG_TRANS"])))

    days: dict[str, list[dict]] = defaultdict(list)
    for (accession, code, day), group in tranches.items():
        submission = submissions[accession]
        owner = owners.get(accession, {})
        relationship = owner.get("RPTOWNER_RELATIONSHIP", "")
        role = role_for(officer="Officer" in relationship, director="Director" in relationship,
                        title=owner.get("RPTOWNER_TITLE"))
        days[_dataset_day(submission["FILING_DATE"])].append(_record(
            int(submission["ISSUERCIK"]), accession, _person_name(owner.get("RPTOWNERNAME", "")),
            display_role(role, ten_percent="TenPercentOwner" in relationship), code, day, group,
            submission.get("AFF10B5ONE", "").strip().lower() in ("1", "true"),
        ))
    return dict(days)


def dataset_links(html: str) -> list[tuple[str, str]]:
    links = []
    for href, quarter in DATASET_LINK.findall(html):
        url = href if href.startswith("http") else "https://www.sec.gov" + href
        if quarter not in {q for q, _ in links}:
            links.append((quarter, url))
    return links


class InsiderStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def has(self, day: str) -> bool:
        return (self.directory / f"{day}.json").exists()

    def write(self, day: str, records: list[dict]) -> None:
        (self.directory / f"{day}.json").write_text(json.dumps(records, ensure_ascii=False, separators=(",", ":")))

    def is_empty(self) -> bool:
        return not any(self.directory.glob("????-??-??.json"))

    def prune(self, today: date, history_days: int = HISTORY_DAYS) -> None:
        """Days older than the history window are no longer needed."""
        cutoff = (today - timedelta(days=history_days + 14)).isoformat()
        for path in self.directory.glob("????-??-??.json"):
            if path.stem < cutoff:
                path.unlink()

    def datasets(self) -> set[str]:
        path = self.directory / "datasets.json"
        return set(json.loads(path.read_text())) if path.exists() else set()

    def mark_dataset(self, quarter: str) -> None:
        (self.directory / "datasets.json").write_text(json.dumps(sorted(self.datasets() | {quarter})))

    def load(self, since: date) -> dict[int, list[dict]]:
        """Records filed since `since`, grouped by company."""
        by_company: dict[int, list[dict]] = defaultdict(list)
        for path in sorted(self.directory.glob("????-??-??.json")):
            if path.stem >= since.isoformat():
                for record in json.loads(path.read_text()):
                    by_company[record["cik"]].append(record)
        return dict(by_company)

    def coverage_start(self, today: date, history_days: int = HISTORY_DAYS) -> date:
        """First day of the unbroken run of stored business days that reaches up to now."""
        day = today - timedelta(days=INDEX_GRACE_DAYS + 1)
        start = day + timedelta(days=1)
        oldest = today - timedelta(days=history_days)
        while day >= oldest:
            if day.weekday() < 5:
                if not self.has(day.isoformat()):
                    break
                start = day
            day -= timedelta(days=1)
        return max(start, oldest)


def backfill(client, store: InsiderStore, today: date, budget: Budget, log=print,
             history_days: int = HISTORY_DAYS) -> None:
    oldest = today - timedelta(days=history_days)
    store.prune(today, history_days)
    _load_datasets(client, store, oldest, log)

    missing = [day for day in _business_days(oldest, today - timedelta(days=1)) if not store.has(day.isoformat())]
    for day in reversed(missing):  # newest first: recent months matter most
        if not budget.allows():
            log(f"Insider-Budget aufgebraucht, {len(missing)} Tage fehlen noch")
            return
        budget.spend()
        index = client.get_text(index_url(day), absent_codes=(403, 404))
        if index is None:
            if (today - day).days > INDEX_GRACE_DAYS:
                store.write(day.isoformat(), [])  # holiday
            continue
        entries = [entry for entry in parse_form_index(index, {"4"})]
        if not budget.allows(len(entries)):
            log(f"Insider-Budget reicht nicht für {day} ({len(entries)} Meldungen)")
            return
        budget.spend(len(entries))
        store.write(day.isoformat(), [record for accession, filing in fetch_filings(client, entries, log)
                                      for record in records_from_filing(filing, accession)])
        missing.remove(day)
    log("Insider-Historie vollständig")


def fetch_filings(client, entries, log=print) -> list[tuple[str, InsiderFiling]]:
    """Downloads and parses Form 4 filings; malformed ones are skipped."""
    filings = []
    for number, entry in enumerate(entries, start=1):
        if number % 250 == 0:
            log(f"Form 4 {number}/{len(entries)} ({entry.filed})")
        xml = extract_ownership_xml(client.get_text(ARCHIVES + entry.path) or "")
        if not xml:
            continue
        try:
            filings.append((entry.path.rsplit("/", 1)[-1].removesuffix(".txt"), parse_form4(xml)))
        except Exception as error:  # malformed filings must not stop the run
            log(f"Form 4 übersprungen ({entry.path}): {error}")
    return filings


def insider_profile(records: list[dict], today: date, since: date,
                    max_value: float | None = None) -> tuple[dict, list[dict]]:
    """Summary of the last year plus the latest transactions, in the app's format."""
    year_ago = (today - timedelta(days=HISTORY_DAYS)).isoformat()
    seen: set[tuple] = set()
    kept = []
    for record in sorted(records, key=lambda r: (r["date"], r["acc"])):
        # Joint filers each report the same trade; count it once.
        key = (record["date"], record["code"], record["shares"], record["price"])
        value = record["shares"] * record["price"]
        if record["date"] < year_ago or key in seen or (max_value is not None and value > max_value):
            continue
        seen.add(key)
        kept.append(record)

    def side(code: str) -> dict:
        chosen = [r for r in kept if r["code"] == code]
        return {"count": len(chosen), "people": len({r["name"] for r in chosen}),
                "value": round(sum(r["shares"] * r["price"] for r in chosen))}

    sells = side("S")
    sells["planned"] = sum(1 for r in kept if r["code"] == "S" and r["planned"])
    summary = {"since": max(since, today - timedelta(days=HISTORY_DAYS)).isoformat(), "buys": side("P"), "sells": sells,
               "byPerson": _by_person(kept)}

    latest = sorted(kept, key=lambda r: r["date"], reverse=True)[:MAX_TRANSACTIONS]
    transactions = [{
        "name": r["name"], "role": tidy_role(r["role"]), "date": r["date"], "kind": "buy" if r["code"] == "P" else "sell",
        "shares": r["shares"], "price": round(r["price"], 2), "value": round(r["shares"] * r["price"]),
        "sharesAfter": r["after"], "planned": r["planned"],
    } for r in latest]
    return summary, transactions


def _by_person(records: list[dict]) -> list[dict]:
    """The people who traded the most, with what they bought and sold in total."""
    people: dict[str, dict] = {}
    for record in sorted(records, key=lambda r: r["date"]):
        person = people.setdefault(record["name"], {"name": record["name"], "bought": 0, "sold": 0, "trades": 0})
        person["role"] = tidy_role(record["role"])  # the latest one
        person["bought" if record["code"] == "P" else "sold"] += round(record["shares"] * record["price"])
        person["trades"] += 1
    ranked = sorted(people.values(), key=lambda p: p["bought"] + p["sold"], reverse=True)[:MAX_PEOPLE]
    return [{"name": p["name"], "role": p["role"], "bought": p["bought"], "sold": p["sold"], "trades": p["trades"]}
            for p in ranked]


def _load_datasets(client, store: InsiderStore, oldest: date, log) -> None:
    page = client.get_text(DATASETS_PAGE)
    if not page:
        log("Insider-Datensätze nicht erreichbar")
        return
    done = store.datasets()
    for quarter, url in dataset_links(page):
        first, last = _quarter_range(quarter)
        if quarter in done or last < oldest:
            continue
        archive = client.get_bytes(url)
        if not archive:
            continue
        days = parse_dataset(archive)
        for day in _business_days(first, last):
            store.write(day.isoformat(), days.get(day.isoformat(), []))
        store.mark_dataset(quarter)
        log(f"Insider-Datensatz {quarter}: {sum(len(r) for r in days.values())} Transaktionen")


def _quarter_range(quarter: str) -> tuple[date, date]:
    year, number = int(quarter[:4]), int(quarter[-1])
    first = date(year, 3 * number - 2, 1)
    last = date(year + (number == 4), (3 * number) % 12 + 1, 1) - timedelta(days=1)
    return first, last


def _business_days(first: date, last: date) -> list[date]:
    days = []
    day = first
    while day <= last:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def _tsv(archive: zipfile.ZipFile, name: str):
    csv.field_size_limit(1 << 30)
    with archive.open(name) as raw:
        yield from csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", errors="replace"),
                                  delimiter="\t", quoting=csv.QUOTE_NONE)


def _dataset_day(text: str) -> str:
    return datetime.strptime(text.strip(), "%d-%b-%Y").date().isoformat()


def _number(text: str | None) -> float | None:
    try:
        return float(text) if text else None
    except ValueError:
        return None


def _whole(value: float | None) -> int | None:
    return round(value) if value is not None else None
