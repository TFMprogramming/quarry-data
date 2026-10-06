from datetime import date

from quarry.prices import close_for, closes_request, parse_closes

CSV = """ts_event,rtype,publisher_id,instrument_id,open,high,low,close,volume,symbol
2026-10-01T00:00:00.000000000Z,35,90,1,100.0,110.0,99.0,105.5,1000,MU
2026-10-02T00:00:00.000000000Z,35,90,1,105.0,112.0,104.0,111.25,1000,MU
2026-10-05T00:00:00.000000000Z,35,90,1,111.0,115.0,110.0,114.0,1000,MU
2026-10-02T00:00:00.000000000Z,35,90,2,400.0,410.0,399.0,405.0,10,BRK.B
"""


def test_latest_close_per_symbol_that_is_at_least_a_day_old():
    closes = parse_closes(CSV, last_day=date(2026, 10, 2))
    assert closes == {"MU": ("2026-10-02", 111.25), "BRK.B": ("2026-10-02", 405.0)}


def test_sec_share_class_tickers_match_dots():
    closes = {"BRK.B": ("2026-10-02", 405.0)}
    assert close_for("BRK-B", closes) == ("2026-10-02", 405.0)
    assert close_for("XYZ", closes) is None


def test_request_covers_the_last_week_up_to_two_days_ago():
    params = closes_request(date(2026, 10, 6))
    assert params["dataset"] == "EQUS.SUMMARY"
    assert params["schema"] == "ohlcv-1d"
    assert params["symbols"] == "ALL_SYMBOLS"
    assert (params["start"], params["end"]) == ("2026-09-28", "2026-10-05")
    assert params["encoding"] == "csv" and params["map_symbols"] == "true" and params["pretty_px"] == "true"
