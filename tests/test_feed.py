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


def test_profile_carries_insiders_holders_events_balance_and_checks():
    submissions = dict(SUBMISSIONS, fiscalYearEnd="0903",
                       addresses={"business": {"city": "BOISE", "stateOrCountry": "ID", "isForeignLocation": 0}},
                       filings={"recent": {"form": ["8-K"], "filingDate": ["2026-09-30"], "items": ["2.02"],
                                           "accessionNumber": ["0000-26-1"], "primaryDocument": ["a.htm"]}})
    sale = {"cik": 1, "acc": "a1", "name": "Ann Lee", "role": "CEO", "code": "S", "date": "2026-09-01",
            "shares": 1000, "price": 10.0, "after": 5000, "planned": True}
    holders = [{"name": "Starboard Value LP", "percent": 13.4, "date": "2026-09-11", "activist": True}]
    company = build_company(1, [INSIDER], submissions, FACTS, TODAY, insider_records=[sale],
                            insider_since=date(2025, 10, 3), holders=holders)
    assert company["about"] == {"location": "Boise, ID", "fiscalYearEndMonth": 9}
    assert company["insiderSummary"]["sells"] == {"count": 1, "people": 1, "value": 10000, "planned": 1}
    assert company["insiderTransactions"][0]["kind"] == "sell"
    assert company["holders"] == holders
    assert company["events"][0]["title"] == "Quartalszahlen veröffentlicht"
    assert "balance" in company and "checks" in company


def test_without_insider_history_there_is_no_summary():
    company = build_company(1, [INSIDER], SUBMISSIONS, FACTS, TODAY)
    assert company["insiderSummary"] is None
    assert company["insiderTransactions"] == []


def _valued(sector_pe):
    from quarry.valuation import ValuationContext
    facts = {"facts": {
        "dei": FACTS["facts"]["dei"] | {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
            {"end": "2026-07-20", "val": 10_000_000, "accn": "k"}]}}},
        "us-gaap": FACTS["facts"]["us-gaap"] | {
            "NetIncomeLoss": {"units": {"USD": [{"start": "2025-07-01", "end": "2026-06-30", "val": 50_000_000}]}}},
    }}
    medians = {"Halbleiter": {"pe": sector_pe, "ps": 3.0, "count": 20}} if sector_pe else {}
    semis = dict(SUBMISSIONS, sic="3674")
    return build_company(1, [INSIDER], semis, facts, TODAY,
                         valuation_context=ValuationContext({"ABCD": ("2026-10-01", 30.0)}, medians))


def test_value_signal_when_pe_is_well_below_the_sector():
    company = _valued(sector_pe=20.0)
    value = {s["kind"]: s for s in company["signals"]}["value"]
    assert value["isActive"] is True
    assert value["headline"] == "KGV 6 · Branche 20"
    assert company["valuation"]["pe"] == 6.0 and company["valuation"]["sectorPe"] == 20.0


def test_value_signal_stays_off_near_the_sector_or_without_peers():
    assert {s["kind"]: s for s in _valued(sector_pe=8.0)["signals"]}["value"]["isActive"] is False
    no_peers = {s["kind"]: s for s in _valued(sector_pe=None)["signals"]}["value"]
    assert no_peers["isActive"] is False and no_peers["headline"] == "KGV 6"


def test_without_prices_value_signal_is_unavailable():
    value = {s["kind"]: s for s in build_company(1, [INSIDER], SUBMISSIONS, FACTS, TODAY)["signals"]}["value"]
    assert value["isActive"] is False and value["headline"] == "Keine Kursdaten"
