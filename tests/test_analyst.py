from datetime import date

from quarry.analyst import analyst_signals, closes_from_bulk, estimate_summary, revision, surprises

TODAY = date(2026, 10, 6)


def _pit(period, field, value, as_of):
    return {"ticker": "MU", "field": field, "period": period, "value": str(value), "as_of_date": as_of}


PIT = [
    # Older snapshot with a different estimate for the coming quarter.
    _pit("2026-12-31", "eps_estimate", 30.0, "2026-09-01"),
    _pit("2026-12-31", "eps_estimate", 36.0, "2026-10-05"),
    *[_pit(p, f, v, "2026-10-05") for p, f, v in [
        ("2025-12-31", "eps_estimate", 4.07), ("2025-12-31", "eps_actual", 4.78),
        ("2026-03-31", "eps_estimate", 9.58), ("2026-03-31", "eps_actual", 12.20),
        ("2026-06-30", "eps_estimate", 21.40), ("2026-06-30", "eps_actual", 25.11),
        ("2026-09-30", "eps_estimate", 32.56), ("2026-09-30", "eps_actual", 33.42),
        ("2025-09-30", "eps_estimate", 2.95), ("2025-09-30", "eps_actual", 2.90),
    ]],
]

ESTIMATES = [
    {"period": "2027-08-31", "year": 2027, "epsEstimate": 173.77, "epsAnalysts": 24},
    {"period": "2026-08-31", "year": 2026, "epsEstimate": 73.85, "epsAnalysts": 25},
    {"period": "2028-08-31", "year": 2028, "epsEstimate": 207.75, "epsAnalysts": 12},
]


def test_surprises_use_the_latest_snapshot_per_quarter():
    assert surprises(PIT) == [
        {"period": "2025-09-30", "estimate": 2.95, "actual": 2.90},
        {"period": "2025-12-31", "estimate": 4.07, "actual": 4.78},
        {"period": "2026-03-31", "estimate": 9.58, "actual": 12.20},
        {"period": "2026-06-30", "estimate": 21.40, "actual": 25.11},
        {"period": "2026-09-30", "estimate": 32.56, "actual": 33.42},
    ]


def test_revision_of_the_coming_quarter_over_thirty_days():
    assert revision(PIT, TODAY) == {"period": "2026-12-31", "now": 36.0, "before": 30.0, "change": 0.2}


def test_revision_needs_a_month_of_history():
    recent = [_pit("2026-12-31", "eps_estimate", 30.0, "2026-09-25"), _pit("2026-12-31", "eps_estimate", 36.0, "2026-10-05")]
    assert revision(recent, TODAY) is None


def test_estimate_summary_takes_the_next_fiscal_year():
    assert estimate_summary(ESTIMATES, TODAY) == {
        "year": 2027, "period": "2027-08-31", "eps": 173.77, "analysts": 24, "previousEps": 73.85, "growth": 1.353,
    }


def test_signals_beat_outlook_and_tailwind():
    signals = {s["kind"]: s for s in analyst_signals(estimate_summary(ESTIMATES, TODAY), surprises(PIT),
                                                     revision(PIT, TODAY))}
    assert signals["beat"]["isActive"] and signals["beat"]["headline"] == "4 von 4 Quartalen über der Schätzung"
    assert signals["outlook"]["isActive"] and signals["outlook"]["headline"] == "Gewinn je Aktie +135 % erwartet (24 Analysten)"
    assert signals["revisions"]["isActive"] and signals["revisions"]["headline"] == "Schätzung +20 % in 30 Tagen"


def test_few_analysts_or_a_miss_switch_signals_off():
    thin = [dict(e, epsAnalysts=1) for e in ESTIMATES]
    missed = [*surprises(PIT)[:-1], {"period": "2026-09-30", "estimate": 32.56, "actual": 30.0}]
    signals = {s["kind"]: s for s in analyst_signals(estimate_summary(thin, TODAY), missed, None)}
    assert not signals["outlook"]["isActive"] and "1 Analyst" in signals["outlook"]["headline"]
    assert not signals["beat"]["isActive"]
    assert not signals["revisions"]["isActive"]


def test_closes_from_bulk_rows():
    rows = [{"ticker": "MU", "payload": [{"symbol": "MU", "date": "2026-10-05", "close": "1063.96"}]},
            {"ticker": "X.KS", "payload": [{"symbol": "X.KS", "date": "2026-10-05", "close": "5"}]}]
    assert closes_from_bulk(rows, {"MU", "BRK-B"}) == {"MU": ("2026-10-05", 1063.96)}


class FakeEulerpool:
    def __init__(self):
        self.requests = 0
        self.monthly_remaining = 50_000
        self.has_quota = True

    def get(self, path):
        self.requests += 1
        if path.startswith("/api/1/datasets/eod-bulk"):
            return {"total": 1, "data": [{"ticker": "MU", "payload": [{"symbol": "MU", "date": "2026-10-05", "close": "1000"}]}]}
        if path.startswith("/api/1/equity/estimates/MU"):
            return ESTIMATES
        if path.startswith("/api/1/equity/pit/estimates/MU"):
            return PIT
        return None


def test_run_writes_private_valuations_signals_and_a_ranking_out_of_seven(tmp_path):
    import json
    from quarry.analyst import run
    from quarry.budget import Budget

    public = {
        "index": [[723125, "MU", "Micron Technology Inc", "Nasdaq"], [1, "ZZZ", "Zzz Corp", "NYSE"]],
        "fundamentals": {"723125": {"tickers": ["MU"], "sector": "Halbleiter", "netIncome": 50e9, "revenue": 90e9,
                                    "shares": 1.13e9, "quarterIncome": 28e9, "quarter": "2026-Q2"}},
        "upswing": {"723125": {"cik": 723125, "ticker": "MU", "name": "Micron Technology Inc", "exchange": "Nasdaq",
                               "sector": "Halbleiter", "score": 3, "isNew": False, "revenueGrowth": 3.46,
                               "signals": [{"kind": "acceleration", "headline": "Umsatz +346 %", "isNew": False}]}},
    }
    run(FakeEulerpool(), TODAY, tmp_path / "data", tmp_path / "out", public, Budget(100), log=lambda m: None)

    analyst = json.loads((tmp_path / "out" / "analyst.json").read_text())
    micron = analyst["companies"]["723125"]
    assert micron["valuation"]["pe"] == 22.6 and micron["valuation"]["forwardPe"] == 5.8
    assert [s["kind"] for s in micron["signals"] if s["isActive"]] == ["beat", "outlook", "revisions"]
    ranking = json.loads((tmp_path / "out" / "ranking.json").read_text())
    assert ranking["maxScore"] == 7
    assert ranking["companies"][0]["score"] == 6
    assert [s["kind"] for s in ranking["companies"][0]["signals"]] == ["acceleration", "beat", "outlook", "revisions"]
    assert (tmp_path / "data" / "analyst.json").exists()
