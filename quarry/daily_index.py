"""EDGAR daily form index: which filings arrived on a given day."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class IndexEntry:
    form: str
    cik: int
    filed: date
    path: str


def index_url(day: date) -> str:
    quarter = (day.month - 1) // 3 + 1
    return f"https://www.sec.gov/Archives/edgar/daily-index/{day.year}/QTR{quarter}/form.{day:%Y%m%d}.idx"


def parse_form_index(text: str, forms: set[str]) -> list[IndexEntry]:
    entries: list[IndexEntry] = []
    seen_accessions: set[str] = set()
    in_data = False

    for line in text.splitlines():
        if line.startswith("-----"):
            in_data = True
            continue
        parts = line.split()
        if not in_data or len(parts) < 4 or parts[0] not in forms:
            continue
        # Company names contain spaces, so read the fixed fields from the right.
        path, filed, cik = parts[-1], parts[-2], parts[-3]
        # A filing is listed once per filer (issuer and each owner), each time under
        # that filer's directory – the accession number at the end is what's shared.
        accession = path.rsplit("/", 1)[-1]
        if accession in seen_accessions:
            continue
        seen_accessions.add(accession)
        entries.append(IndexEntry(parts[0], int(cik), datetime.strptime(filed, "%Y%m%d").date(), path))

    return entries
