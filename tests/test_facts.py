from quarry.facts import public_float, quarters, revenue_growth

FACTS = {"facts": {
    "dei": {"EntityPublicFloat": {"units": {"USD": [
        {"val": 6154360, "filed": "2024-11-26"},
        {"val": 840000000, "filed": "2025-11-25"},
    ]}}},
    "us-gaap": {
        "Revenues": {"units": {"USD": [
            {"val": 90, "frame": "CY2017Q2", "filed": "2017-08-01"},
        ]}},
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
            {"val": 100, "frame": "CY2025Q2", "filed": "2025-08-01"},
            {"val": 300, "frame": "CY2025", "filed": "2026-02-01"},
            {"val": 148, "frame": "CY2026Q2", "filed": "2026-08-01"},
        ]}},
        "NetIncomeLoss": {"units": {"USD": [
            {"val": 12, "frame": "CY2026Q2", "filed": "2026-08-01"},
        ]}},
    },
}}


def test_public_float_uses_latest_filing():
    assert public_float(FACTS) == 840000000


def test_quarters_merge_concepts_and_skip_annual_frames():
    result = quarters(FACTS)
    assert [q.period for q in result] == ["2017-Q2", "2025-Q2", "2026-Q2"]
    assert result[-1].revenue == 148 and result[-1].net_income == 12


def test_revenue_growth_compares_same_quarter_last_year():
    period, growth = revenue_growth(FACTS)
    assert period == "2026-Q2"
    assert round(growth, 2) == 0.48


def test_missing_data_is_none():
    assert public_float({"facts": {}}) is None
    assert revenue_growth({"facts": {}}) is None


def _usd(*entries):
    return {"units": {"USD": [dict(zip(("start", "end", "val", "accn"), e)) for e in entries]}}


BALANCE_FACTS = {"facts": {
    "us-gaap": {
        "CashAndCashEquivalentsAtCarryingValue": _usd((None, "2026-02-26", 13_000, "a"), (None, "2026-05-28", 25_000, "b")),
        "AvailableForSaleSecuritiesDebtSecuritiesCurrent": _usd((None, "2026-05-28", 1_000, "b")),
        "LongTermDebt": _usd((None, "2025-11-27", 8_800, "x")),
        "LongTermDebtNoncurrent": _usd((None, "2026-05-28", 9_000, "b")),
        "LongTermDebtCurrent": _usd((None, "2026-05-28", 500, "b")),
        # Year to date: fiscal year starts 2025-08-29.
        "NetCashProvidedByUsedInOperatingActivities": _usd(
            ("2024-08-30", "2025-08-28", 18_000, "k"),  # last fiscal year
            ("2024-08-30", "2025-05-29", 11_000, "p"),  # same nine months a year earlier
            ("2025-08-29", "2026-05-28", 45_000, "b"),
        ),
        "PaymentsToAcquirePropertyPlantAndEquipment": _usd(
            ("2024-08-30", "2025-08-28", 15_000, "k"),
            ("2024-08-30", "2025-05-29", 10_000, "p"),
            ("2025-08-29", "2026-05-28", 19_000, "b"),
        ),
    },
    "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
        {"end": "2025-06-18", "val": 1_000, "accn": "p"},
        {"end": "2026-06-17", "val": 1_100, "accn": "b"},
        {"end": "2026-06-17", "val": 100, "accn": "b"},  # second share class in the same filing
    ]}}},
}}


def test_balance_uses_latest_values_and_trailing_twelve_months():
    from quarry.facts import balance
    assert balance(BALANCE_FACTS) == {
        "date": "2026-05-28",
        "cash": 26_000,
        "debt": 9_500,
        "shares": 1_200,
        "sharesChange": 0.2,
        # 45,000 + 18,000 − 11,000 operating, minus 19,000 + 15,000 − 10,000 investment
        "operatingCashFlow": 52_000,
        "freeCashFlow": 28_000,
    }


def test_balance_of_empty_facts_is_none():
    from quarry.facts import balance
    assert balance({"facts": {}}) is None
