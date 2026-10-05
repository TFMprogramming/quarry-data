"""Every US-listed company, from the SEC's ticker/exchange directory."""
from __future__ import annotations

from dataclasses import dataclass

DIRECTORY_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
LISTED = {"Nasdaq", "NYSE", "NYSE American", "NYSE Arca", "CBOE"}


@dataclass(frozen=True)
class DirectoryEntry:
    cik: int
    ticker: str
    name: str
    exchange: str


def parse_directory(raw: dict) -> list[DirectoryEntry]:
    fields = raw.get("fields", [])
    entries = []
    for row in raw.get("data", []):
        record = dict(zip(fields, row))
        if record.get("exchange") in LISTED and record.get("ticker"):
            entries.append(DirectoryEntry(
                cik=int(record["cik"]),
                ticker=str(record["ticker"]).upper(),
                name=display_name(str(record.get("name") or record["ticker"])),
                exchange=record["exchange"],
            ))
    return entries


def index_json(entries: list[DirectoryEntry]) -> dict:
    return {"version": 1, "companies": [[e.cik, e.ticker, e.name, e.exchange] for e in entries]}


def display_name(name: str) -> str:
    # str.title() would turn "DICK'S" into "Dick'S"; capitalise word by word instead.
    return " ".join(word.capitalize() for word in name.split()) if name.isupper() else name
