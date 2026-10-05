"""Form 4: insider transactions. We only care about open-market purchases."""
from __future__ import annotations

import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from datetime import date

TITLE_SHORTCUTS = [
    ("chief executive", "CEO"),
    ("chief financial", "CFO"),
    ("chief operating", "COO"),
    ("chief technology", "CTO"),
    ("chairman", "Chairman"),
    ("president", "President"),
]


@dataclass
class Purchase:
    date: date
    shares: float
    price: float

    @property
    def value(self) -> float:
        return self.shares * self.price


@dataclass
class InsiderFiling:
    issuer_cik: int
    ticker: str
    issuer_name: str
    owner_name: str
    role: str | None  # None for owners who are neither officer nor director
    purchases: list[Purchase] = field(default_factory=list)


def extract_ownership_xml(submission: str) -> str | None:
    start = submission.find("<ownershipDocument>")
    end = submission.find("</ownershipDocument>")
    if start == -1 or end == -1:
        return None
    return submission[start:end + len("</ownershipDocument>")]


def parse_form4(xml_text: str) -> InsiderFiling:
    root = ElementTree.fromstring(xml_text)
    relationship = root.find("reportingOwner/reportingOwnerRelationship")

    purchases = []
    for transaction in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        code = _text(transaction, "transactionCoding/transactionCode")
        acquired = _text(transaction, "transactionAmounts/transactionAcquiredDisposedCode/value")
        shares = _number(transaction, "transactionAmounts/transactionShares/value")
        price = _number(transaction, "transactionAmounts/transactionPricePerShare/value")
        when = _text(transaction, "transactionDate/value")
        if code == "P" and acquired == "A" and shares > 0 and price > 0 and when:
            purchases.append(Purchase(date.fromisoformat(when[:10]), shares, price))

    return InsiderFiling(
        issuer_cik=int(_text(root, "issuer/issuerCik") or 0),
        ticker=(_text(root, "issuer/issuerTradingSymbol") or "").upper(),
        issuer_name=_text(root, "issuer/issuerName") or "",
        owner_name=_person_name(_text(root, "reportingOwner/reportingOwnerId/rptOwnerName") or ""),
        role=_role(relationship),
        purchases=purchases,
    )


def _role(relationship) -> str | None:
    if relationship is None:
        return None
    if _flag(relationship, "isOfficer"):
        title = (_text(relationship, "officerTitle") or "").strip()
        lowered = title.lower()
        for needle, shortcut in TITLE_SHORTCUTS:
            if needle in lowered:
                return shortcut
        return title if 0 < len(title) <= 20 else "Vorstand"
    if _flag(relationship, "isDirector"):
        return "Direktor"
    return None


NAME_SUFFIXES = {"JR", "JR.", "SR", "SR.", "II", "III", "IV"}


def _person_name(sec_name: str) -> str:
    """SEC writes 'Last First Middle [Suffix]'; turn it into 'First Middle Last [Suffix]'."""
    parts = sec_name.split()
    if len(parts) < 2:
        return sec_name.title() if sec_name.isupper() else sec_name
    suffix = [parts.pop()] if parts[-1].upper() in NAME_SUFFIXES else []
    ordered = parts[1:] + parts[:1] + suffix
    return " ".join(_name_case(part) for part in ordered)


def _name_case(part: str) -> str:
    if part.upper() in NAME_SUFFIXES:
        return part.upper().replace("JR", "Jr").replace("SR", "Sr")
    return part.capitalize() if part.isupper() else part


def _flag(element, path: str) -> bool:
    return (_text(element, path) or "").strip().lower() in ("1", "true")


def _text(element, path: str) -> str | None:
    found = element.find(path)
    return found.text.strip() if found is not None and found.text else None


def _number(element, path: str) -> float:
    try:
        return float(_text(element, path) or 0)
    except ValueError:
        return 0.0
