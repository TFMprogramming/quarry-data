from datetime import date

from quarry.form4 import InsiderFiling, Purchase
from quarry.signals import insider_events, momentum_event

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


def test_momentum_event_needs_twenty_percent():
    assert momentum_event(7, DAY, ("2026-Q2", 0.25))["growth"] == 0.25
    assert momentum_event(7, DAY, ("2026-Q2", 0.10)) is None
    assert momentum_event(7, DAY, None) is None
