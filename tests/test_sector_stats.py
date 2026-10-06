from datetime import date

from quarry.sector_stats import MIN_COMPANIES, sector_overview

TODAY = date(2026, 10, 6)


def _company(cik, sector, score, growth):
    return {"cik": cik, "ticker": f"T{cik}", "name": f"Firma {cik}", "exchange": "NYSE", "sector": sector,
            "score": score, "isNew": False, "revenueGrowth": growth, "signals": []}


def _entries(*companies):
    return {str(c["cik"]): c for c in companies}


def test_sectors_ranked_by_share_in_upswing():
    semis = [_company(i, "Halbleiter", 3 if i < 4 else 0, 0.1 * i) for i in range(10)]
    banks = [_company(100 + i, "Banken", 2 if i == 0 else 1, 0.02) for i in range(10)]
    overview = sector_overview(_entries(*semis, *banks), TODAY)
    assert [s["name"] for s in overview["sectors"]] == ["Halbleiter", "Banken"]
    semis_stats = overview["sectors"][0]
    assert (semis_stats["companies"], semis_stats["upswing"], semis_stats["share"]) == (10, 4, 0.4)
    assert semis_stats["medianGrowth"] == 0.45
    # Members: strongest first, as [cik, ticker, name, score, growth].
    assert semis_stats["members"][0] == [3, "T3", "Firma 3", 3, 0.3]


def test_small_sectors_are_grouped_and_shells_left_out():
    small = [_company(200 + i, "Tabak", 0, 0.01) for i in range(MIN_COMPANIES - 1)]
    shells = [_company(300 + i, "Mantelgesellschaften", 0, None) for i in range(20)]
    overview = sector_overview(_entries(*small, *shells), TODAY)
    assert [s["name"] for s in overview["sectors"]] == []
    assert overview["other"]["companies"] == MIN_COMPANIES - 1


def test_growth_median_ignores_missing_values():
    companies = [_company(i, "Chemie", 0, None if i % 2 else 0.2) for i in range(MIN_COMPANIES * 2)]
    assert sector_overview(_entries(*companies), TODAY)["sectors"][0]["medianGrowth"] == 0.2
