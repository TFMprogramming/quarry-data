from datetime import date

from quarry.feed import build_company

TODAY = date(2026, 10, 3)
SUBMISSIONS = {"name": "ABCD ROBOTICS INC", "tickers": ["ABCD"], "exchanges": ["Nasdaq"], "sicDescription": "Industrial Machinery"}
FACTS = {"facts": {
    "dei": {"EntityPublicFloat": {"units": {"USD": [{"val": 840_000_000, "filed": "2026-02-01"}]}}},
    "us-gaap": {"Revenues": {"units": {"USD": [
        {"val": 100, "frame": "CY2025Q2"}, {"val": 150, "frame": "CY2026Q2"},
    ]}}},
}}
INSIDER = {"kind": "insider", "cik": 1, "ticker": "ABCD", "date": "2026-10-02", "value": 480_000,
           "trades": [{"name": "Margaret Olsen", "role": "CEO", "date": "2026-10-01", "shares": 20500, "value": 480_000}]}


def test_builds_company_with_signals_and_trigger():
    company = build_company(1, [INSIDER], SUBMISSIONS, FACTS, TODAY)
    assert company["name"] == "Abcd Robotics Inc"
    assert company["tradingViewSymbol"] == "NASDAQ:ABCD"
    assert company["trigger"] == {"kind": "insider", "headline": "CEO kaufte für 480.000 $", "date": "2026-10-02"}
    signals = {s["kind"]: s for s in company["signals"]}
    assert [s["kind"] for s in company["signals"]] == ["value", "overlooked", "insider", "trend"]
    assert signals["value"]["isActive"] is False
    assert signals["overlooked"]["isActive"] is True
    assert signals["insider"]["isActive"] and signals["insider"]["isNew"]
    assert signals["trend"]["isActive"] and signals["trend"]["headline"] == "Umsatz +50 %"
    # 3 active + 0.5 new + 0.5 for ≥ 250k
    assert company["importance"] == 4.0


def test_unlisted_company_is_skipped():
    otc = dict(SUBMISSIONS, exchanges=["OTC"])
    assert build_company(1, [INSIDER], otc, FACTS, TODAY) is None


def test_several_buyers_headline():
    event = dict(INSIDER, trades=INSIDER["trades"] + [{"name": "Bob", "role": "Direktor", "date": "2026-10-01", "shares": 1, "value": 20_000}], value=500_000)
    company = build_company(1, [event], SUBMISSIONS, FACTS, TODAY)
    assert company["trigger"]["headline"] == "2 Insider kauften für 500.000 $"


def test_purchase_larger_than_public_float_is_ignored():
    tiny = {"facts": {"dei": {"EntityPublicFloat": {"units": {"USD": [{"val": 8_400_000, "filed": "2026-02-01"}]}}}}}
    bogus = dict(INSIDER, value=92_412_000, trades=[dict(INSIDER["trades"][0], value=92_412_000)])
    assert build_company(1, [bogus], SUBMISSIONS, tiny, TODAY) is None


def test_display_name_keeps_apostrophes_lowercase():
    from quarry.feed import _display_name
    assert _display_name("DICK'S SPORTING GOODS, INC.") == "Dick's Sporting Goods, Inc."
    assert _display_name("Oracle Corp") == "Oracle Corp"


def test_profile_without_recent_events_has_no_trigger():
    old = dict(INSIDER, date="2026-08-01")
    company = build_company(1, [old], SUBMISSIONS, FACTS, TODAY, require_recent=False)
    assert company["trigger"] is None
    assert {s["kind"]: s for s in company["signals"]}["insider"]["isActive"]
    assert build_company(1, [old], SUBMISSIONS, FACTS, TODAY) is None


def test_tradingview_symbol_uses_dots_for_share_classes():
    berkshire = dict(SUBMISSIONS, tickers=["BRK-B"], exchanges=["NYSE"])
    assert build_company(1, [INSIDER], berkshire, FACTS, TODAY)["tradingViewSymbol"] == "NYSE:BRK.B"


def test_sector_is_german_and_original_kept():
    semis = dict(SUBMISSIONS, sic="3674", sicDescription="Semiconductors & Related Devices")
    company = build_company(1, [INSIDER], semis, FACTS, TODAY)
    assert company["sector"] == "Halbleiter"
    assert company["industry"] == "Semiconductors & Related Devices"
