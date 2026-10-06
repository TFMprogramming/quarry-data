from datetime import date

from quarry.quarters import current, quarter_table, year_ago


def _entry(start, end, val, filed="2026-01-01"):
    return {"start": start, "end": end, "val": val, "filed": filed}


def _facts(**concepts):
    return {"facts": {"us-gaap": {name: {"units": {"USD": entries}} for name, entries in concepts.items()}}}


FISCAL = [  # fiscal year Sep–Aug: Q1–Q3 reported alone, Q4 only inside the annual figure
    _entry("2024-08-30", "2024-11-28", 100),
    _entry("2024-11-29", "2025-02-27", 110),
    _entry("2024-11-29", "2025-02-27", 111, filed="2026-03-01"),  # corrected in a later filing
    _entry("2025-02-28", "2025-05-29", 120),
    _entry("2024-08-30", "2025-08-28", 460, filed="2025-10-01"),  # full year
    _entry("2024-08-30", "2025-05-29", 330),  # nine months year to date – ignored
]


def test_fourth_quarter_is_derived_from_the_year():
    table = quarter_table(_facts(Revenues=FISCAL))
    assert [(q.end.isoformat(), q.revenue) for q in table] == [
        ("2024-11-28", 100), ("2025-02-27", 111), ("2025-05-29", 120), ("2025-08-28", 129),
    ]
    assert table[-1].filed == date(2025, 10, 1)
    assert table[1].filed == date(2026, 1, 1)  # first known, not the later correction


def test_gross_profit_from_cost_of_revenue_and_margins():
    facts = _facts(
        Revenues=[_entry("2025-01-01", "2025-03-31", 200)],
        CostOfRevenue=[_entry("2025-01-01", "2025-03-31", 150)],
        NetIncomeLoss=[_entry("2025-01-01", "2025-03-31", 20)],
        OperatingIncomeLoss=[_entry("2025-01-01", "2025-03-31", 30)],
    )
    quarter = quarter_table(facts)[0]
    assert (quarter.gross_profit, quarter.net_income, quarter.operating_income) == (50, 20, 30)
    assert (quarter.gross_margin, quarter.operating_margin) == (0.25, 0.15)


def test_year_ago_allows_shifting_fiscal_calendars():
    table = quarter_table(_facts(Revenues=[
        _entry("2024-03-03", "2024-06-01", 80), _entry("2025-03-02", "2025-05-31", 120),
    ]))
    assert year_ago(table, table[-1]).revenue == 80


def test_losses_stay_negative_and_feed_the_fourth_quarter():
    table = quarter_table(_facts(Revenues=FISCAL, NetIncomeLoss=[
        _entry("2024-08-30", "2024-11-28", -5), _entry("2024-11-29", "2025-02-27", -4),
        _entry("2025-02-28", "2025-05-29", -3), _entry("2024-08-30", "2025-08-28", -10, filed="2025-10-01"),
    ]))
    assert [q.net_income for q in table] == [-5, -4, -3, 2]


def test_stale_tables_are_dropped():
    table = quarter_table(_facts(Revenues=FISCAL))
    assert current(table, date(2025, 12, 1)) == table
    assert current(table, date(2026, 10, 6)) == []
