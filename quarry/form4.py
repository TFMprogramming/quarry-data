"""Form 4: insider transactions. Open-market purchases drive the insider
signal; purchases and sales together make up a company's insider history."""
from __future__ import annotations

import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from datetime import date

TITLE_SHORTCUTS = [
    ("chief executive", "CEO"),
    ("principal executive", "CEO"),
    ("chief financial", "CFO"),
    ("principal financial", "CFO"),
    ("chief operating", "COO"),
    ("chief technology", "CTO"),
    ("chief accounting", "CAO"),
    ("principal accounting", "CAO"),
    ("general counsel", "Chefjurist"),
    ("chief legal", "Chefjurist"),
    ("chairman", "Chairman"),
    ("president", "President"),
]
# Abbreviations in titles; "PEO/PFO/PAO" are the SEC's principal officers.
TITLE_ABBREVIATIONS = {"ceo": "CEO", "peo": "CEO", "cfo": "CFO", "pfo": "CFO", "coo": "COO", "cto": "CTO",
                       "cao": "CAO", "pao": "CAO"}


@dataclass
class Purchase:
    date: date
    shares: float
    price: float

    @property
    def value(self) -> float:
        return self.shares * self.price


@dataclass
class Transaction:
    """An open-market purchase ("P") or sale ("S")."""
    code: str
    date: date
    shares: float
    price: float
    shares_after: float | None
    planned: bool  # under a pre-arranged 10b5-1 trading plan


@dataclass
class InsiderFiling:
    issuer_cik: int
    ticker: str
    issuer_name: str
    owner_name: str
    role: str | None  # None for owners who are neither officer nor director
    purchases: list[Purchase] = field(default_factory=list)
    transactions: list[Transaction] = field(default_factory=list)
    display_role: str = "Insider"  # also covers large holders, for lists


def extract_ownership_xml(submission: str) -> str | None:
    start = submission.find("<ownershipDocument>")
    end = submission.find("</ownershipDocument>")
    if start == -1 or end == -1:
        return None
    return submission[start:end + len("</ownershipDocument>")]


def parse_form4(xml_text: str) -> InsiderFiling:
    root = ElementTree.fromstring(xml_text)
    relationship = root.find("reportingOwner/reportingOwnerRelationship")

    planned = _flag(root, "aff10b5One")

    purchases = []
    transactions = []
    for transaction in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        code = _text(transaction, "transactionCoding/transactionCode")
        acquired = _text(transaction, "transactionAmounts/transactionAcquiredDisposedCode/value")
        shares = _number(transaction, "transactionAmounts/transactionShares/value")
        price = _number(transaction, "transactionAmounts/transactionPricePerShare/value")
        when = _text(transaction, "transactionDate/value")
        if not when or shares <= 0 or price <= 0:
            continue
        day = date.fromisoformat(when[:10])
        if code == "P" and acquired == "A":
            purchases.append(Purchase(day, shares, price))
        if (code, acquired) in (("P", "A"), ("S", "D")):
            after = _text(transaction, "postTransactionAmounts/sharesOwnedFollowingTransaction/value")
            transactions.append(Transaction(code, day, shares, price, _float(after), planned))

    return InsiderFiling(
        issuer_cik=int(_text(root, "issuer/issuerCik") or 0),
        ticker=(_text(root, "issuer/issuerTradingSymbol") or "").upper(),
        issuer_name=_text(root, "issuer/issuerName") or "",
        owner_name=_person_name(_text(root, "reportingOwner/reportingOwnerId/rptOwnerName") or ""),
        role=_role(relationship),
        purchases=purchases,
        transactions=transactions,
        display_role=_display_role(relationship),
    )


def _role(relationship) -> str | None:
    if relationship is None:
        return None
    return role_for(
        officer=_flag(relationship, "isOfficer"),
        director=_flag(relationship, "isDirector"),
        title=_text(relationship, "officerTitle"),
    )


def _display_role(relationship) -> str:
    if relationship is None:
        return "Insider"
    return display_role(_role(relationship), ten_percent=_flag(relationship, "isTenPercentOwner"))


def display_role(role: str | None, ten_percent: bool) -> str:
    if role:
        return role
    return "Großaktionär" if ten_percent else "Insider"


def role_for(officer: bool, director: bool, title: str | None) -> str | None:
    """Short role of an officer or director; None for everyone else."""
    if officer:
        return officer_title(title)
    if director:
        return "Direktor"
    return None


def officer_title(title: str | None) -> str:
    """'EVP and CFO' -> 'CFO'; unknown short titles stay, long ones become 'Vorstand'."""
    title = (title or "").strip()
    lowered = title.lower()
    words = lowered.replace(",", " ").replace("/", " ").replace("&", " ").replace(".", "").split()
    for word in words:  # the first abbreviation wins: "CEO and CFO" -> CEO
        if word in TITLE_ABBREVIATIONS:
            return TITLE_ABBREVIATIONS[word]
    for needle, shortcut in TITLE_SHORTCUTS:
        if needle in lowered:
            return shortcut
    return title if 0 < len(title) <= 20 else "Vorstand"


KNOWN_ROLES = {"Direktor", "Großaktionär", "Insider", "Vorstand"}


def tidy_role(role: str) -> str:
    """Re-reads stored roles with the current title rules."""
    return role if role in KNOWN_ROLES else officer_title(role)


NAME_SUFFIXES = {"JR", "JR.", "SR", "SR.", "II", "III", "IV"}
# Words that mark a fund or company rather than a person.
ENTITY_WORDS = {
    "INC", "INC.", "LLC", "L.L.C.", "LP", "L.P.", "LTD", "LTD.", "CORP", "CORP.", "CO", "CO.", "PLC", "AG", "SA",
    "N.V.", "NV", "FUND", "FUNDS", "TRUST", "CAPITAL", "PARTNERS", "HOLDINGS", "HOLDING", "MANAGEMENT", "GROUP",
    "ADVISORS", "ADVISERS", "INVESTMENTS", "INVESTMENT", "BANK", "ASSOCIATES", "VENTURES", "FOUNDATION", "LLP",
    "MASTER", "OPPORTUNITIES", "EQUITY", "SECURITIES", "LIMITED", "COMPANY", "GMBH",
}


def _person_name(sec_name: str) -> str:
    """SEC writes 'Last First Middle [Suffix]'; turn it into 'First Middle Last [Suffix]'.
    Funds and companies keep their order."""
    if any(word.upper().strip(",") in ENTITY_WORDS for word in sec_name.split()):
        return " ".join(_entity_case(part) for part in sec_name.split())
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


def _entity_case(part: str) -> str:
    """'GROUP' -> 'Group', but legal forms like 'LP' or 'LLC' stay as they are."""
    if not part.isupper() or part.strip(",.") in {"LP", "LLC", "LLP", "PLC", "AG", "SA", "NV", "II", "III", "IV"}:
        return part
    return part.capitalize()


def _float(text: str | None) -> float | None:
    try:
        return float(text) if text else None
    except ValueError:
        return None


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
