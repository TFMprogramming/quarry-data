from datetime import date

from quarry.daily_index import index_url, parse_form_index

SAMPLE = """Form Type   Company Name                                                  CIK         Date Filed  File Name
---------------------------------------------------------------------------------------------------------------------------------------------
10-Q             DARDEN RESTAURANTS INC                                        940944      20261002    edgar/data/940944/0000940944-26-000042.txt
4                325 CAPITAL LLC                                               1873893     20261002    edgar/data/1873893/0000921895-26-002714.txt
4                325 Capital GP, LLC                                           1972758     20261002    edgar/data/1972758/0000921895-26-002714.txt
4/A              Some Amendment Inc                                            1111        20261002    edgar/data/1111/0000000000-26-000001.txt
8-K              Other Corp                                                    2222        20261002    edgar/data/2222/0000000000-26-000002.txt
"""


def test_keeps_requested_forms_and_dedupes_paths():
    entries = parse_form_index(SAMPLE, {"4", "10-Q"})
    assert [(e.form, e.cik) for e in entries] == [("10-Q", 940944), ("4", 1873893)]
    assert entries[1].path == "edgar/data/1873893/0000921895-26-002714.txt"
    assert entries[0].filed == date(2026, 10, 2)


def test_index_url_uses_quarter():
    assert index_url(date(2026, 10, 2)).endswith("/2026/QTR4/form.20261002.idx")
