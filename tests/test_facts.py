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
