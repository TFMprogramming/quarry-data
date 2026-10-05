from quarry.directory import index_json, parse_directory

RAW = {"fields": ["cik", "name", "ticker", "exchange"], "data": [
    [320193, "Apple Inc.", "AAPL", "Nasdaq"],
    [723125, "MICRON TECHNOLOGY INC", "MU", "Nasdaq"],
    [1652044, "Alphabet Inc.", "GOOGL", "Nasdaq"],
    [1652044, "Alphabet Inc.", "GOOG", "Nasdaq"],
    [1, "Some Pink Sheet Co", "PINK", "OTC"],
    [2, "No Exchange Co", "NOEX", None],
]}


def test_keeps_listed_tickers_including_share_classes():
    entries = parse_directory(RAW)
    assert [e.ticker for e in entries] == ["AAPL", "MU", "GOOGL", "GOOG"]


def test_display_cases_shouting_names():
    entries = {e.ticker: e for e in parse_directory(RAW)}
    assert entries["MU"].name == "Micron Technology Inc"
    assert entries["AAPL"].name == "Apple Inc."


def test_index_is_compact():
    index = index_json(parse_directory(RAW))
    assert index["version"] == 1
    assert index["companies"][0] == [320193, "AAPL", "Apple Inc.", "Nasdaq"]
