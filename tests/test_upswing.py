from datetime import date, timedelta

from quarry.quarters import QuarterFigures
from quarry.upswing import UpswingStore, upswing_signals

TODAY = date(2026, 10, 6)


def _table(revenues, incomes=None, gross=None, last_filed=date(2026, 10, 1)):
    """Quarters ending every 91 days, the newest last."""
    count = len(revenues)
    first_end = date(2026, 9, 30) - timedelta(days=91 * (count - 1))
    table = []
    for i, revenue in enumerate(revenues):
        end = first_end + timedelta(days=91 * i)
        table.append(QuarterFigures(
            start=end - timedelta(days=90), end=end,
            filed=last_filed if i == count - 1 else end + timedelta(days=30),
            revenue=revenue,
            net_income=incomes[i] if incomes else None,
            gross_profit=gross[i] if gross else None,
        ))
    return table


def _kinds(signals, active=True):
    return [s["kind"] for s in signals if s["isActive"] == active]


def test_accelerating_revenue():
    # Year-on-year: 100->110 (+10 %), then 100->140 (+40 %).
    signals = upswing_signals(_table([100, 100, 100, 100, 100, 110, 100, 140]), TODAY)
    acceleration = {s["kind"]: s for s in signals}["acceleration"]
    assert acceleration["isActive"] and acceleration["isNew"]
    assert acceleration["headline"] == "Umsatz +40 % (Vorquartal +0 %)"


def test_steady_growth_is_not_acceleration():
    signals = upswing_signals(_table([100, 100, 100, 100, 130, 130, 130, 130]), TODAY)
    assert "acceleration" in _kinds(signals, active=False)


def test_turnaround_after_losses():
    signals = upswing_signals(_table([100] * 8, incomes=[-5, -4, -3, -2, -1, -1, 3, 5]), TODAY)
    turnaround = {s["kind"]: s for s in signals}["turnaround"]
    assert turnaround["isActive"] and turnaround["headline"] == "Gewinn nach Verlusten"


def test_profit_growing_faster_than_revenue():
    signals = upswing_signals(_table([100, 100, 100, 100, 100, 100, 100, 120],
                                     incomes=[10, 10, 10, 10, 10, 10, 10, 20]), TODAY)
    assert {s["kind"]: s for s in signals}["turnaround"]["headline"] == "Gewinn +100 % (Umsatz +20 %)"


def test_expanding_margin():
    signals = upswing_signals(_table([100] * 8, gross=[30, 30, 30, 30, 30, 30, 30, 36]), TODAY)
    margin = {s["kind"]: s for s in signals}["margin"]
    assert margin["isActive"] and margin["headline"] == "Bruttomarge 36 % (Vorjahr 30 %)"


def test_old_report_is_not_new():
    signals = upswing_signals(_table([100, 100, 100, 100, 100, 110, 100, 140], last_filed=date(2026, 8, 1)), TODAY)
    assert {s["kind"]: s for s in signals}["acceleration"]["isNew"] is False


def test_without_quarters_all_signals_are_off():
    assert _kinds(upswing_signals([], TODAY)) == []
    assert len(upswing_signals([], TODAY)) == 3


def test_store_ranks_companies_and_spots_newcomers(tmp_path):
    store = UpswingStore(tmp_path / "upswing.json")

    def company(cik, active, new=False):
        signals = [{"kind": kind, "isActive": kind in active, "isNew": new and kind in active, "headline": kind.upper(),
                    "detail": ""} for kind in ("acceleration", "turnaround", "margin", "insider")]
        return {"cik": cik, "ticker": f"T{cik}", "name": f"Firma {cik}", "exchange": "NYSE", "sector": "Chemie",
                "signals": signals, "upswing": {"score": len(active), "isNew": new, "revenueGrowth": 0.3}}

    store.record(company(1, {"acceleration", "margin"}))
    store.record(company(2, {"acceleration", "turnaround", "margin"}, new=True))
    store.record(company(3, {"insider"}))
    store.record(dict(company(4, set()), upswing=None))
    ranking = store.ranking(TODAY)
    assert [c["cik"] for c in ranking["companies"]] == [2, 1]
    assert ranking["companies"][0]["signals"] == [
        {"kind": "acceleration", "headline": "ACCELERATION", "isNew": True},
        {"kind": "turnaround", "headline": "TURNAROUND", "isNew": True},
        {"kind": "margin", "headline": "MARGIN", "isNew": True},
    ]
    assert ranking["maxScore"] == 4 and ranking["companies"][0]["isNew"] is True
