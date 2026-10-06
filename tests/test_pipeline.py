import json
from datetime import date

from quarry.daily_index import index_url
from quarry.pipeline import run
from tests.test_form4 import XML

IDX = """Form Type   Company Name   CIK   Date Filed  File Name
-----------------------------------------------------------------
4                WOODWARD INC                                                  108312      20261002    edgar/data/108312/0001.txt
"""


class FakeClient:
    def __init__(self, responses):
        self.responses = responses

    def get_text(self, url, **kwargs):
        return self.responses.get(url)

    def get_json(self, url):
        text = self.get_text(url)
        return json.loads(text) if text else None


def test_run_writes_events_and_feed(tmp_path):
    responses = {
        index_url(date(2026, 10, 2)): IDX,
        "https://www.sec.gov/Archives/edgar/data/108312/0001.txt": "<XML>" + XML + "</XML>",
        "https://data.sec.gov/submissions/CIK0000108312.json": json.dumps(
            {"name": "Woodward, Inc.", "tickers": ["WWD"], "exchanges": ["Nasdaq"], "sicDescription": "Electrical"}),
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000108312.json": json.dumps({"facts": {}}),
    }
    feed_path = tmp_path / "public" / "feed.json"
    run(FakeClient(responses), today=date(2026, 10, 3), data_dir=tmp_path / "data", feed_path=feed_path,
        process_days=2, log=lambda message: None, closes={"WWD": ("2026-10-01", 200.0)})

    assert (tmp_path / "data" / "events" / "2026-10-02.json").exists()
    insiders = json.loads((tmp_path / "data" / "insiders" / "2026-10-02.json").read_text())
    assert [(r["cik"], r["code"], r["name"]) for r in insiders] == [(108312, "P", "Margaret Olsen")]
    feed = json.loads(feed_path.read_text())
    assert feed["version"] == 1
    assert [c["ticker"] for c in feed["companies"]] == ["WWD"]
    assert feed["companies"][0]["trigger"]["headline"] == "CEO kaufte für 479.700 $"
    assert feed["companies"][0]["insiderSummary"]["buys"]["count"] == 1
    # No share count in the fake facts, so no valuation – but the file is written for the app.
    assert feed["companies"][0]["valuation"] is None
    assert json.loads((tmp_path / "public" / "valuations.json").read_text())["version"] == 1
    ranking = json.loads((tmp_path / "public" / "upswing.json").read_text())
    assert ranking["maxScore"] == 4 and ranking["companies"] == []  # one signal is not enough
    assert json.loads((tmp_path / "public" / "sectors.json").read_text())["version"] == 1
