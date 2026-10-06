from datetime import date

from quarry.form4 import InsiderFiling, Purchase
from quarry.signals import insider_events

DAY = date(2026, 10, 2)


def filing(owner, role, value, cik=1, ticker="ABCD"):
    return InsiderFiling(cik, ticker, "Abcd Corp", owner, role, [Purchase(DAY, value / 10, 10.0)])


def test_aggregates_purchases_per_issuer_and_applies_threshold():
    events = insider_events([
        filing("Ann", "CEO", 20_000),
        filing("Bob", "Direktor", 10_000),
        filing("Fund", None, 900_000),  # 10 % owner: ignored
        filing("Cid", "CFO", 5_000, cik=2, ticker="SMAL"),  # below threshold
    ], DAY)
    assert len(events) == 1
    event = events[0]
    assert event["kind"] == "insider" and event["cik"] == 1 and event["value"] == 30_000
    assert [trade["name"] for trade in event["trades"]] == ["Ann", "Bob"]
    assert event["date"] == "2026-10-02"


