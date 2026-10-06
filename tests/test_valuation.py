import json
from datetime import date

from quarry.valuation import FundamentalsStore, ValuationContext, basis, sector_medians, valuation, valuations_json


def _usd(*entries):
    return {"units": {"USD": [dict(zip(("start", "end", "val", "accn"), e)) for e in entries]}}


FACTS = {"facts": {
    "us-gaap": {
        "NetIncomeLoss": {"units": {"USD": [
            {"start": "2025-07-01", "end": "2026-06-30", "val": 50_000_000, "accn": "k"},
            {"start": "2026-04-01", "end": "2026-06-30", "val": 25_000_000, "accn": "k", "frame": "CY2026Q2"},
        ]}},
        "Revenues": _usd(("2025-07-01", "2026-06-30", 400_000_000, "k")),
    },
    "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
        {"end": "2026-07-20", "val": 10_000_000, "accn": "k"}]}}},
}}
SUBMISSIONS = {"tickers": ["ABCD"], "exchanges": ["Nasdaq"], "filings": {"recent": {"form": ["10-K", "8-K"]}}}
CLOSES = {"ABCD": ("2026-10-02", 30.0)}


def test_basis_from_sec_figures():
    assert basis(FACTS, SUBMISSIONS, "Halbleiter") == {
        "tickers": ["ABCD"], "sector": "Halbleiter", "netIncome": 50_000_000, "revenue": 400_000_000,
        "shares": 10_000_000, "quarterIncome": 25_000_000, "quarter": "2026-Q2",
    }


def test_foreign_filers_have_no_basis():
    # Their share counts are ordinary shares, the listed ticker is often an ADR.
    foreign = dict(SUBMISSIONS, filings={"recent": {"form": ["20-F", "6-K"]}})
    assert basis(FACTS, foreign, "Halbleiter") is None


def test_valuation_from_close_and_basis():
    assert valuation(basis(FACTS, SUBMISSIONS, "Halbleiter"), CLOSES) == {
        "date": "2026-10-02", "price": 30.0, "marketCap": 300_000_000, "pe": 6.0, "ps": 0.75,
        "peRunRate": 3.0, "quarter": "2026-Q2",
    }


def test_losses_have_no_pe_and_share_classes_with_different_prices_are_skipped():
    losing = dict(basis(FACTS, SUBMISSIONS, "Halbleiter"), netIncome=-5)
    assert valuation(losing, CLOSES)["pe"] is None
    classes = dict(basis(FACTS, SUBMISSIONS, "X"), tickers=["BRK-A", "BRK-B"])
    assert valuation(classes, {"BRK.A": ("2026-10-02", 600_000.0), "BRK.B": ("2026-10-02", 400.0)}) is None
    assert valuation(dict(classes, tickers=["GOOGL", "GOOG"]),
                     {"GOOGL": ("2026-10-02", 200.0), "GOOG": ("2026-10-02", 201.0)})["price"] == 200.0


def _peers(sector, *pes):
    return {str(i): {"tickers": [f"T{sector}{i}"], "sector": sector, "netIncome": 100.0, "revenue": 1000.0,
                     "shares": 1.0} for i, _ in enumerate(pes)}, \
        {f"T{sector}{i}": ("2026-10-02", pe * 100.0) for i, pe in enumerate(pes)}


def test_sector_medians_need_enough_peers():
    bases, closes = _peers("Chemie", 10, 12, 14, 16, 18, 20, 22, 24)
    small, small_closes = _peers("Tabak", 5, 6)
    medians = sector_medians({**bases, **{"s" + k: v for k, v in small.items()}}, {**closes, **small_closes})
    assert medians == {"Chemie": {"pe": 17.0, "ps": 1.7, "count": 8}}


def test_context_values_a_company_against_its_sector_and_remembers_its_basis(tmp_path):
    store = FundamentalsStore(tmp_path / "fundamentals.json")
    context = ValuationContext(CLOSES, {"Halbleiter": {"pe": 20.0, "ps": 3.0, "count": 30}}, store)
    result = context.value(723125, basis(FACTS, SUBMISSIONS, "Halbleiter"))
    assert (result["pe"], result["sectorPe"], result["sectorPs"]) == (6.0, 20.0, 3.0)
    store.save()
    assert json.loads((tmp_path / "fundamentals.json").read_text())["723125"]["shares"] == 10_000_000


def test_valuations_json_lists_every_priced_company(tmp_path):
    store = FundamentalsStore(tmp_path / "f.json")
    store.entries["1"] = basis(FACTS, SUBMISSIONS, "Halbleiter")
    data = valuations_json(store, CLOSES, date(2026, 10, 6))
    assert data["version"] == 1 and data["date"] == "2026-10-02"
    assert data["companies"] == {"1": [30.0, 300_000_000, 6.0, 0.75, 3.0]}
    assert data["sectors"] == {}
