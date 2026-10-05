import json
from datetime import date

from quarry.directory import DirectoryEntry
from quarry.profiles import build_profiles, is_due

TUESDAY = date(2026, 10, 6)  # weekday() == 1


def test_rotation_by_cik():
    assert is_due(cik=11, today=TUESDAY, exists=True, feed_ciks=set())      # 11 % 5 == 1
    assert not is_due(cik=12, today=TUESDAY, exists=True, feed_ciks=set())


def test_missing_profiles_and_feed_companies_are_always_due():
    assert is_due(cik=12, today=TUESDAY, exists=False, feed_ciks=set())
    assert is_due(cik=12, today=TUESDAY, exists=True, feed_ciks={12})


class FakeClient:
    def __init__(self):
        self.calls = []

    def get_json(self, url):
        self.calls.append(url)
        if "submissions" in url:
            return {"name": "MICRON TECHNOLOGY INC", "tickers": ["MU"], "exchanges": ["Nasdaq"], "sic": "3674", "sicDescription": "Semiconductors"}
        return {"facts": {}}


def test_builds_profile_without_recent_event(tmp_path):
    entries = [DirectoryEntry(723125, "MU", "Micron Technology Inc", "Nasdaq")]
    written = build_profiles(FakeClient(), entries, {}, TUESDAY, tmp_path, feed_ciks=set(), log=lambda m: None)
    assert written == 1
    profile = json.loads((tmp_path / "723125.json").read_text())
    assert profile["ticker"] == "MU"
    assert profile["trigger"] is None
    assert profile["sector"] == "Halbleiter"


def test_skips_profiles_that_are_not_due(tmp_path):
    (tmp_path / "723127.json").write_text("{}")  # 723127 % 5 == 2, exists
    entries = [DirectoryEntry(723127, "XYZ", "Xyz", "Nasdaq")]
    client = FakeClient()
    assert build_profiles(client, entries, {}, TUESDAY, tmp_path, feed_ciks=set(), log=lambda m: None) == 0
    assert client.calls == []
