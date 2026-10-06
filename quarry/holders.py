"""Large shareholders: who reported owning 5 % or more (Schedule 13D/13G).
13D means the holder may want to influence the company; 13G is passive."""
from __future__ import annotations

import json
import xml.etree.ElementTree as ElementTree
from datetime import date, timedelta
from pathlib import Path

from quarry.budget import Budget
from quarry.form4 import _entity_case

HISTORY_DAYS = 550  # 13G updates come once a year; keep a little more than that
THRESHOLD = 5.0  # below 5 % a holder no longer has to report – and is no longer a large holder
HOLDER_FORMS = {"SCHEDULE 13D", "SCHEDULE 13D/A", "SCHEDULE 13G", "SCHEDULE 13G/A"}


def parse_schedule13(xml_text: str) -> dict | None:
    root = ElementTree.fromstring(xml_text)
    for element in root.iter():
        element.tag = element.tag.rsplit("}", 1)[-1]  # drop namespaces

    names = [_clean(e.text) for e in root.iter("reportingPersonName") if e.text]
    percents = [_number(e.text) for e in root.iter() if e.tag in ("classPercent", "percentOfClass")]
    shares = [_number(e.text) for e in root.iter()
              if e.tag in ("aggregateAmountOwned", "reportingPersonBeneficiallyOwnedAggregateNumberOfShares")]
    filer = root.find("headerData/filerInfo/filer/filerCredentials/cik")
    issuer = next((e.text for e in root.iter() if e.tag in ("issuerCik", "issuerCIK") and e.text), None)
    if not names or filer is None:
        return None
    return {
        "filer": int(filer.text),
        "issuer": int(issuer) if issuer else None,
        "name": names[0],
        "percent": max((p for p in percents if p is not None), default=None),
        "shares": round(max((s for s in shares if s is not None), default=0)),
        "activist": "13D" in (root.findtext("headerData/submissionType") or ""),
    }


class HolderCache:
    """Parsed filings by accession number. Filings never change, so this only grows."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.entries: dict[str, dict | None] = json.loads(self.path.read_text()) if self.path.exists() else {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.entries, ensure_ascii=False, separators=(",", ":")))


def holders_for(client, cik: int, submissions: dict, cache: HolderCache, today: date, budget: Budget) -> list[dict]:
    """The latest reported stake of each holder that still holds 5 % or more, largest first.

    A company's filing list also holds the stakes it reports in *other*
    companies; only filings about this company count."""
    recent = submissions.get("filings", {}).get("recent", {})
    oldest = (today - timedelta(days=HISTORY_DAYS)).isoformat()
    latest: dict[int, dict] = {}
    rows = zip(recent.get("form", []), recent.get("filingDate", []), recent.get("accessionNumber", []),
               recent.get("primaryDocument", []))
    for form, filed, accession, document in sorted(rows, key=lambda row: row[1]):
        if form not in HOLDER_FORMS or filed < oldest:
            continue
        if accession not in cache.entries:
            if not budget.allows():
                continue
            budget.spend()
            xml = client.get_text(_document_url(cik, accession, document))
            try:
                cache.entries[accession] = parse_schedule13(xml) if xml else None
            except ElementTree.ParseError:
                cache.entries[accession] = None
        parsed = cache.entries[accession]
        if parsed and parsed["percent"] is not None and parsed.get("issuer") == cik:
            latest[parsed["filer"]] = {"name": parsed["name"], "percent": parsed["percent"], "date": filed,
                                       "activist": parsed["activist"]}
    current = [holder for holder in latest.values() if holder["percent"] >= THRESHOLD]
    return sorted(current, key=lambda holder: holder["percent"], reverse=True)


def _document_url(cik: int, accession: str, document: str) -> str:
    # "xslSCHEDULE_13G_X02/primary_doc.xml" is the rendered view; the raw XML sits one level up.
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{document.rsplit('/', 1)[-1]}"


def _clean(name: str) -> str:
    return " ".join(_entity_case(part) for part in name.split())


def _number(text: str | None) -> float | None:
    try:
        return float(text) if text else None
    except ValueError:
        return None
