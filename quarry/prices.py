"""Official end-of-day closing prices for every US-listed stock, from the
Databento US Equities Summary data set (consolidated across all exchanges).

Prices are only passed on once they are more than a day old: that is when
Databento's data may be redistributed. For a P/E ratio a close from two days
ago is just as good."""
from __future__ import annotations

import base64
import csv
import io
import urllib.parse
import urllib.request
from datetime import date, timedelta

DATABENTO_URL = "https://hist.databento.com/v0/timeseries.get_range"
DATASET = "EQUS.SUMMARY"
# Closes of the day before yesterday and earlier: more than 24 hours old at the 05:00 UTC run.
DELAY_DAYS = 2
LOOKBACK_DAYS = 8  # covers long weekends and holidays

Close = tuple[str, float]  # (trading day, closing price)


def closes_request(today: date) -> dict[str, str]:
    return {
        "dataset": DATASET,
        "symbols": "ALL_SYMBOLS",
        "schema": "ohlcv-1d",
        "stype_in": "raw_symbol",
        "start": (today - timedelta(days=LOOKBACK_DAYS)).isoformat(),
        # Exclusive end: the last included day is `DELAY_DAYS` ago.
        "end": (today - timedelta(days=DELAY_DAYS - 1)).isoformat(),
        "encoding": "csv",
        "compression": "none",
        "pretty_px": "true",
        "pretty_ts": "true",
        "map_symbols": "true",
    }


def fetch_closes(api_key: str, today: date, opener=urllib.request.urlopen, log=print) -> dict[str, Close]:
    """Ticker -> latest close. Empty if the request fails – valuations then simply wait a day."""
    body = urllib.parse.urlencode(closes_request(today)).encode()
    token = base64.b64encode(f"{api_key}:".encode()).decode()
    request = urllib.request.Request(DATABENTO_URL, data=body, method="POST",
                                     headers={"Authorization": f"Basic {token}"})
    try:
        with opener(request, timeout=300) as response:
            text = response.read().decode("utf-8", errors="replace")
    except Exception as error:  # a missing price day must not stop the feed
        log(f"Schlusskurse nicht verfügbar: {error}")
        return {}
    closes = parse_closes(text, today - timedelta(days=DELAY_DAYS))
    log(f"Schlusskurse: {len(closes)} Kürzel")
    return closes


def parse_closes(csv_text: str, last_day: date) -> dict[str, Close]:
    closes: dict[str, Close] = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        symbol, day, close = row.get("symbol"), (row.get("ts_event") or "")[:10], row.get("close")
        if not symbol or not day or not close or day > last_day.isoformat():
            continue
        try:
            price = float(close)
        except ValueError:
            continue
        if price > 0 and (symbol not in closes or day > closes[symbol][0]):
            closes[symbol] = (day, price)
    return closes


def close_for(ticker: str, closes: dict[str, Close]) -> Close | None:
    """SEC writes share classes as 'BRK-B', the exchanges as 'BRK.B'."""
    for candidate in (ticker, ticker.replace("-", "."), ticker.replace("-", "/"), ticker.replace("-", " ")):
        if candidate in closes:
            return closes[candidate]
    return None
