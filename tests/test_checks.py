from quarry.checks import health_checks
from quarry.facts import Quarter


def _quarters(*incomes):
    return [Quarter(f"2026-Q{i + 1}", 100.0, income) for i, income in enumerate(incomes)]


def test_loss_maker_with_short_runway_and_dilution():
    checks = health_checks(
        _quarters(-10e6, -12e6, -9e6, -11e6),
        {"cash": 30e6, "debt": 0, "freeCashFlow": -40e6, "sharesChange": 0.35},
        [{"kind": "warning", "title": "Wirtschaftsprüfer gewechselt", "date": "2026-08-01"},
         {"kind": "warning", "title": "Wirtschaftsprüfer gewechselt", "date": "2026-03-01"}],
    )
    assert [(c["level"], c["title"]) for c in checks] == [
        ("warning", "Macht Verluste"),
        ("warning", "Geld reicht rechnerisch etwa 9 Monate"),
        ("warning", "Aktienzahl +35 % in einem Jahr"),
        ("warning", "Wirtschaftsprüfer gewechselt"),
        ("ok", "Keine Finanzschulden"),
    ]
    assert checks[3]["detail"] == "Kann Routine sein – oder auf Uneinigkeit über die Bilanz hindeuten. Gemeldet am 1.8.2026."
    assert checks[1]["detail"].startswith("Kasse 30,0 Mio. $, Abfluss 40,0 Mio. $ in zwölf Monaten.")


def test_healthy_company():
    checks = health_checks(
        _quarters(10e6, 12e6, 9e6, 11e6),
        {"cash": 500e6, "debt": 200e6, "freeCashFlow": 80e6, "sharesChange": -0.04},
        [],
    )
    assert [(c["level"], c["title"]) for c in checks] == [
        ("ok", "Profitabel"),
        ("ok", "Erwirtschaftet Geld"),
        ("ok", "Kauft eigene Aktien zurück"),
        ("ok", "Mehr Geld als Schulden"),
    ]


def test_without_data_there_are_no_checks():
    assert health_checks([], None, []) == []


def test_profitable_company_burning_cash_is_not_counting_months():
    checks = health_checks(_quarters(10e6, 12e6, 9e6, 11e6), {"cash": 1e9, "freeCashFlow": -4e9}, [])
    assert ("info", "Investiert mehr, als hereinkommt") in [(c["level"], c["title"]) for c in checks]


def test_banks_skip_cash_flow_and_debt():
    checks = health_checks(_quarters(10e6, 12e6, 9e6, 11e6),
                           {"cash": 1e6, "debt": 9e9, "freeCashFlow": -4e9}, [], financial=True)
    assert [c["title"] for c in checks] == ["Profitabel"]
