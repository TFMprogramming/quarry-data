"""A company's notable filings of the last year, in plain German.

Everything comes from the submissions JSON that is loaded for each profile
anyway. Routine paperwork (Form 4, structured notes, exhibits) is left out."""
from __future__ import annotations

from datetime import date, timedelta

HISTORY_DAYS = 365
MAX_EVENTS = 40
# Repeats of the same kind of filing within this many days are shown once.
REPEAT_DAYS = 7

# 8-K items: title and kind. https://www.sec.gov/files/form8-k.pdf
ITEMS = {
    "1.01": ("Wichtiger Vertrag geschlossen", "deal"),
    "1.02": ("Wichtiger Vertrag beendet", "deal"),
    "1.03": ("Insolvenz oder Zwangsverwaltung", "warning"),
    "1.05": ("Cyberangriff gemeldet", "warning"),
    "2.01": ("Übernahme oder Verkauf abgeschlossen", "deal"),
    "2.02": ("Quartalszahlen veröffentlicht", "report"),
    "2.03": ("Neue Schulden aufgenommen", "capital"),
    "2.04": ("Schulden vorzeitig fällig", "warning"),
    "2.05": ("Umbau mit Stellenabbau oder Schließungen", "other"),
    "2.06": ("Wertberichtigung auf Vermögen", "warning"),
    "3.01": ("Börse warnt: Notierung gefährdet", "warning"),
    "3.02": ("Neue Aktien ausgegeben", "capital"),
    "3.03": ("Rechte der Aktionäre geändert", "other"),
    "4.01": ("Wirtschaftsprüfer gewechselt", "warning"),
    "4.02": ("Frühere Zahlen nicht mehr verlässlich", "warning"),
    "5.01": ("Kontrollwechsel", "deal"),
    "5.02": ("Wechsel in Vorstand oder Aufsichtsrat", "people"),
    "5.03": ("Satzung geändert", "other"),
    "5.07": ("Ergebnis der Hauptversammlung", "other"),
    "7.01": ("Präsentation oder Mitteilung", "other"),
    "8.01": ("Sonstige wichtige Mitteilung", "other"),
}
KIND_PRIORITY = ["warning", "deal", "capital", "people", "report", "holder", "other"]

FORMS = {
    "10-K": ("Jahresbericht", "report"),
    "20-F": ("Jahresbericht", "report"),
    "40-F": ("Jahresbericht", "report"),
    "10-Q": ("Quartalsbericht", "report"),
    "10-K/A": ("Jahresbericht nachträglich geändert", "other"),
    "10-Q/A": ("Quartalsbericht nachträglich geändert", "other"),
    "NT 10-K": ("Bericht verspätet angekündigt", "warning"),
    "NT 10-Q": ("Bericht verspätet angekündigt", "warning"),
    "S-1": ("Ausgabe neuer Wertpapiere vorbereitet", "capital"),
    "S-3": ("Ausgabe neuer Wertpapiere vorbereitet", "capital"),
    "F-1": ("Ausgabe neuer Wertpapiere vorbereitet", "capital"),
    "F-3": ("Ausgabe neuer Wertpapiere vorbereitet", "capital"),
    "424B4": ("Neue Aktien oder Anleihen angeboten", "capital"),
    "424B5": ("Neue Aktien oder Anleihen angeboten", "capital"),
    "S-4": ("Fusion oder Übernahme geplant", "deal"),
    "DEFM14A": ("Fusion: Aktionäre stimmen ab", "deal"),
    "SC TO-T": ("Übernahmeangebot für die Aktien", "deal"),
    "SC 14D9": ("Stellungnahme zu einem Übernahmeangebot", "deal"),
    "SCHEDULE 13D": ("Aktiver Großinvestor meldet Anteil", "holder"),
    "SCHEDULE 13D/A": ("Aktiver Großinvestor ändert Anteil", "holder"),
    "SCHEDULE 13G": ("Neuer Großaktionär über 5 %", "holder"),
    "25-NSE": ("Börsennotierung wird beendet", "warning"),
    "25": ("Börsennotierung wird beendet", "warning"),
    "15-12B": ("Abmeldung bei der SEC", "warning"),
    "15-12G": ("Abmeldung bei der SEC", "warning"),
    "DEF 14A": ("Einladung zur Hauptversammlung", "other"),
}


def timeline(cik: int, submissions: dict, today: date, holders_by_accession: dict[str, dict]) -> list[dict]:
    recent = submissions.get("filings", {}).get("recent", {})
    oldest = (today - timedelta(days=HISTORY_DAYS)).isoformat()
    rows = zip(recent.get("form", []), recent.get("filingDate", []), recent.get("items", [""] * 10_000),
               recent.get("accessionNumber", []), recent.get("primaryDocument", []))

    events: list[dict] = []
    last_shown: dict[str, date] = {}
    for form, filed, items, accession, document in sorted(rows, key=lambda row: row[1]):
        if filed < oldest:
            continue
        described = _describe(form, items or "")
        if described is None:
            continue
        title, kind, detail = described
        holder = holders_by_accession.get(accession)
        # Holder filings in a company's list may be its own stakes in other companies.
        if kind == "holder" and not (holder and holder.get("issuer") == cik and holder.get("percent") is not None):
            continue
        day = date.fromisoformat(filed)
        if title in last_shown and (day - last_shown[title]).days < REPEAT_DAYS:
            continue
        last_shown[title] = day
        if kind == "holder":
            detail = f"{holder['name']} · {_percent(holder['percent'])}"
        event = {"date": filed, "title": title, "kind": kind,
                 "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{document}"}
        if detail:
            event["detail"] = detail
        events.append(event)

    return sorted(events, key=lambda event: event["date"], reverse=True)[:MAX_EVENTS]


def _describe(form: str, items: str) -> tuple[str, str, str | None] | None:
    if form in ("8-K", "8-K/A"):
        known = [ITEMS[item] for item in items.split(",") if item.strip() in ITEMS]
        if not known:
            return None
        known.sort(key=lambda entry: KIND_PRIORITY.index(entry[1]))
        others = [title for title, _ in known[1:] if title != known[0][0]]
        return known[0][0], known[0][1], ("Außerdem: " + ", ".join(others)) if others else None
    if form in FORMS:
        return (*FORMS[form], None)
    return None


def _percent(value: float) -> str:
    return f"{value:.1f}".replace(".", ",") + " %"
