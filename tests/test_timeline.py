from datetime import date

from quarry.timeline import timeline

TODAY = date(2026, 10, 6)


def _submissions(*rows):
    return {"filings": {"recent": {
        "form": [r[0] for r in rows], "filingDate": [r[1] for r in rows], "items": [r[2] for r in rows],
        "accessionNumber": [f"0000-26-{i}" for i in range(len(rows))], "primaryDocument": ["doc.htm"] * len(rows),
    }}}


def test_translates_filings_and_picks_the_most_important_8k_item():
    events = timeline(723125, _submissions(
        ("8-K", "2026-09-30", "2.02,9.01", ),
        ("8-K", "2026-08-26", "5.02,7.01,9.01"),
        ("8-K", "2026-08-01", "4.02,2.02"),
        ("4", "2026-08-01", ""),
        ("10-Q", "2026-07-01", ""),
        ("424B2", "2026-07-01", ""),
        ("NT 10-K", "2026-06-01", ""),
        ("8-K", "2025-09-01", "2.02"),  # more than a year ago
    ), TODAY, holders_by_accession={})
    assert [(e["date"], e["title"], e["kind"]) for e in events] == [
        ("2026-09-30", "Quartalszahlen veröffentlicht", "report"),
        ("2026-08-26", "Wechsel in Vorstand oder Aufsichtsrat", "people"),
        ("2026-08-01", "Frühere Zahlen nicht mehr verlässlich", "warning"),
        ("2026-07-01", "Quartalsbericht", "report"),
        ("2026-06-01", "Bericht verspätet angekündigt", "warning"),
    ]
    assert events[2]["detail"] == "Außerdem: Quartalszahlen veröffentlicht"
    assert events[0]["url"] == "https://www.sec.gov/Archives/edgar/data/723125/0000260/doc.htm"


def test_holder_filings_name_the_holder():
    events = timeline(1, _submissions(("SCHEDULE 13D", "2026-09-11", ""), ("SCHEDULE 13G/A", "2026-05-14", "")),
                      TODAY, holders_by_accession={"0000-26-0": {"name": "Starboard Value LP", "percent": 13.4, "issuer": 1}})
    assert [(e["title"], e.get("detail")) for e in events] == [
        ("Aktiver Großinvestor meldet Anteil", "Starboard Value LP · 13,4 %"),
    ]


def test_repeated_offerings_within_a_week_are_shown_once():
    events = timeline(1, _submissions(("424B5", "2026-09-03", ""), ("424B5", "2026-09-01", "")), TODAY, {})
    assert [e["date"] for e in events] == ["2026-09-01"]
