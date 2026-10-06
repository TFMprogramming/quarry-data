import io
import json
import zipfile
from datetime import date

from quarry.budget import Budget
from quarry.form4 import parse_form4
from quarry.insiders import (
    InsiderStore,
    backfill,
    dataset_links,
    insider_profile,
    parse_dataset,
    records_from_filing,
)
from tests.test_form4 import SALE_XML, XML

TODAY = date(2026, 10, 6)


def _record(**changes):
    record = {"cik": 1, "acc": "a1", "name": "Ann Lee", "role": "CEO", "code": "P", "date": "2026-09-01",
              "shares": 1000, "price": 10.0, "after": 5000, "planned": False}
    record.update(changes)
    return record


def test_records_from_filing_merge_tranches_of_one_day():
    filing = parse_form4(SALE_XML.replace("</nonDerivativeTable>", """
  <nonDerivativeTransaction>
   <transactionDate><value>2026-10-01</value></transactionDate>
   <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
   <transactionAmounts>
    <transactionShares><value>500</value></transactionShares>
    <transactionPricePerShare><value>24.40</value></transactionPricePerShare>
    <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
   </transactionAmounts>
   <postTransactionAmounts><sharesOwnedFollowingTransaction><value>79000</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
  </nonDerivativeTransaction>
 </nonDerivativeTable>"""))
    records = records_from_filing(filing, "0001-26-1")
    assert len(records) == 1
    record = records[0]
    assert (record["cik"], record["acc"], record["code"], record["date"]) == (108312, "0001-26-1", "S", "2026-10-01")
    assert record["shares"] == 21000
    assert record["price"] == round((20500 * 23.40 + 500 * 24.40) / 21000, 4)
    assert record["after"] == 79000
    assert record["planned"] is True
    assert record["name"] == "Margaret Olsen" and record["role"] == "CEO"


def _dataset_zip() -> bytes:
    def tsv(header, *rows):
        return "\t".join(header) + "\n" + "".join("\t".join(row) + "\n" for row in rows)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("SUBMISSION.tsv", tsv(
            ["ACCESSION_NUMBER", "FILING_DATE", "DOCUMENT_TYPE", "ISSUERCIK", "AFF10B5ONE"],
            ["0001-26-1", "30-JUN-2026", "4", "0000723125", "1"],
            ["0001-26-2", "29-JUN-2026", "4/A", "0000723125", "0"],
            ["0001-26-3", "29-JUN-2026", "4", "0000000042", "false"],
        ))
        archive.writestr("REPORTINGOWNER.tsv", tsv(
            ["ACCESSION_NUMBER", "RPTOWNERNAME", "RPTOWNER_RELATIONSHIP", "RPTOWNER_TITLE"],
            ["0001-26-1", "MEHROTRA SANJAY", "Director,Officer", "President and CEO"],
            ["0001-26-1", "SOMEONE ELSE", "Director", ""],
            ["0001-26-3", "BIG FUND LP", "TenPercentOwner", ""],
        ))
        archive.writestr("NONDERIV_TRANS.tsv", tsv(
            ["ACCESSION_NUMBER", "TRANS_DATE", "TRANS_CODE", "TRANS_SHARES", "TRANS_PRICEPERSHARE",
             "TRANS_ACQUIRED_DISP_CD", "SHRS_OWND_FOLWNG_TRANS"],
            ["0001-26-1", "26-JUN-2026", "S", "10000.0", "120.5", "D", "90000.0"],
            ["0001-26-1", "26-JUN-2026", "A", "500.0", "0", "A", "100000.0"],
            ["0001-26-2", "26-JUN-2026", "S", "10000.0", "120.5", "D", "90000.0"],
            ["0001-26-3", "25-JUN-2026", "P", "2000.0", "3.0", "A", ""],
        ))
    return buffer.getvalue()


def test_parse_dataset_groups_by_filing_day_and_skips_amendments():
    days = parse_dataset(_dataset_zip())
    assert sorted(days) == ["2026-06-29", "2026-06-30"]
    sale = days["2026-06-30"][0]
    assert (sale["cik"], sale["name"], sale["role"], sale["code"], sale["shares"], sale["after"], sale["planned"]) == \
        (723125, "Sanjay Mehrotra", "CEO", "S", 10000, 90000, True)
    fund = days["2026-06-29"][0]
    assert (fund["name"], fund["role"], fund["after"], fund["planned"]) == ("Big Fund LP", "Großaktionär", None, False)


def test_dataset_links_from_listing_page():
    html = '<a href="/files/x/insider-transactions-data-sets/2026q2_form345.zip">Q2</a>' \
           '<a href="/files/y/insider-transactions-data-sets/2025q4_form345.zip">Q4</a>'
    assert dataset_links(html) == [
        ("2026q2", "https://www.sec.gov/files/x/insider-transactions-data-sets/2026q2_form345.zip"),
        ("2025q4", "https://www.sec.gov/files/y/insider-transactions-data-sets/2025q4_form345.zip"),
    ]


def test_store_coverage_counts_back_from_recent_days(tmp_path):
    store = InsiderStore(tmp_path)
    for day in ["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02"]:
        store.write(day, [])
    # 2026-09-25 (Fri) is missing, so coverage starts on the following Monday.
    assert store.coverage_start(TODAY) == date(2026, 9, 28)
    store.write("2026-09-25", [_record(date="2026-09-24")])
    assert store.coverage_start(TODAY) <= date(2026, 9, 25)
    assert store.load(date(2026, 9, 1)) == {1: [_record(date="2026-09-24")]}


def test_insider_profile_sums_buys_and_sells_and_drops_duplicates():
    records = [
        _record(),
        _record(acc="a2", name="Bo Kim", role="Direktor", shares=200, price=11.0),
        _record(acc="a3", code="S", shares=3000, price=12.0, planned=True, date="2026-09-10"),
        # The same sale reported again by a second, jointly filing owner.
        _record(acc="a4", code="S", shares=3000, price=12.0, planned=True, date="2026-09-10", name="Lee Trust"),
        _record(acc="a5", code="S", date="2025-08-01"),  # older than a year
    ]
    summary, transactions = insider_profile(records, TODAY, since=date(2025, 10, 6))
    assert summary == {
        "since": "2025-10-06",
        "buys": {"count": 2, "people": 2, "value": 12200},
        "sells": {"count": 1, "people": 1, "value": 36000, "planned": 1},
    }
    assert [t["kind"] for t in transactions] == ["sell", "buy", "buy"]
    assert transactions[0] == {"name": "Ann Lee", "role": "CEO", "date": "2026-09-10", "kind": "sell", "shares": 3000,
                               "price": 12.0, "value": 36000, "sharesAfter": 5000, "planned": True}


def test_insider_profile_drops_implausible_values():
    summary, transactions = insider_profile([_record(price=1_000_000.0)], TODAY, since=date(2025, 10, 6), max_value=50_000)
    assert summary["buys"]["count"] == 0 and transactions == []


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get_text(self, url, **kwargs):
        self.calls.append(url)
        return self.responses.get(url)

    def get_bytes(self, url, **kwargs):
        self.calls.append(url)
        return self.responses.get(url)


def test_backfill_uses_datasets_then_fills_recent_days_within_budget(tmp_path):
    from quarry.daily_index import index_url
    from quarry.insiders import DATASETS_PAGE

    idx = """Form Type   Company Name   CIK   Date Filed  File Name
-----------------------------------------------------------------
4                WOODWARD INC                                                  108312      20261002    edgar/data/108312/0001-26-9.txt
"""
    responses = {
        DATASETS_PAGE: '<a href="/files/d/insider-transactions-data-sets/2026q2_form345.zip">x</a>',
        "https://www.sec.gov/files/d/insider-transactions-data-sets/2026q2_form345.zip": _dataset_zip(),
        index_url(date(2026, 10, 2)): idx,
        "https://www.sec.gov/Archives/edgar/data/108312/0001-26-9.txt": "<XML>" + SALE_XML + "</XML>",
    }
    store = InsiderStore(tmp_path)
    client = FakeClient(responses)
    backfill(client, store, TODAY, Budget(4), log=lambda m: None, history_days=120)

    assert "2026q2" in store.datasets()
    assert store.has("2026-06-30")
    assert store.has("2026-06-12")  # a business day without filings in the data set: written empty
    assert store.has("2026-10-02")
    assert store.load(date(2026, 10, 1))[108312][0]["code"] == "S"
    # Budget of four, newest day first: 10-05 (index not out yet, try again next run),
    # 10-02 (index + one filing), 10-01 (no index: a holiday, written empty) – then it's used up.
    assert not store.has("2026-10-05")
    assert store.has("2026-10-01")
    assert not store.has("2026-09-30")

    # A second run continues where the first stopped and does not download the data set again.
    client.calls.clear()
    backfill(client, store, TODAY, Budget(2), log=lambda m: None, history_days=120)
    assert all("form345" not in url for url in client.calls)


def test_prune_drops_days_beyond_the_window(tmp_path):
    store = InsiderStore(tmp_path)
    store.write("2025-09-01", [])
    store.write("2026-09-01", [])
    store.prune(TODAY)
    assert not store.has("2025-09-01") and store.has("2026-09-01")
