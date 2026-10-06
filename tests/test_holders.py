import json
from datetime import date

from quarry.budget import Budget
from quarry.holders import HolderCache, holders_for, parse_schedule13

G = """<?xml version="1.0"?><edgarSubmission xmlns="http://www.sec.gov/edgar/schedule13g">
<headerData><submissionType>SCHEDULE 13G/A</submissionType><filerInfo><filer><filerCredentials><cik>0001422849</cik></filerCredentials></filer></filerInfo></headerData>
<formData><coverPageHeader><eventDateRequiresFilingThisStatement>03/31/2026</eventDateRequiresFilingThisStatement><issuerInfo><issuerCik>0000723125</issuerCik></issuerInfo></coverPageHeader>
<coverPageHeaderReportingPersonDetails><reportingPersonName>Capital World Investors</reportingPersonName>
<reportingPersonBeneficiallyOwnedAggregateNumberOfShares>42208309.00</reportingPersonBeneficiallyOwnedAggregateNumberOfShares>
<classPercent>6.2</classPercent></coverPageHeaderReportingPersonDetails></formData></edgarSubmission>"""

D = """<?xml version="1.0"?><edgarSubmission xmlns="http://www.sec.gov/edgar/schedule13D">
<headerData><submissionType>SCHEDULE 13D</submissionType><filerInfo><filer><filerCredentials><cik>0002156957</cik></filerCredentials></filer></filerInfo></headerData>
<formData><coverPageHeader><dateOfEvent>09/10/2026</dateOfEvent><issuerInfo><issuerCIK>0000723125</issuerCIK></issuerInfo></coverPageHeader><reportingPersons>
<reportingPersonInfo><reportingPersonName>STARBOARD VALUE LP</reportingPersonName><aggregateAmountOwned>701262.00</aggregateAmountOwned><percentOfClass>13.4</percentOfClass></reportingPersonInfo>
<reportingPersonInfo><reportingPersonName>Jeffrey C. Smith</reportingPersonName><aggregateAmountOwned>701262.00</aggregateAmountOwned><percentOfClass>13.4</percentOfClass></reportingPersonInfo>
</reportingPersons></formData></edgarSubmission>"""


def test_parses_passive_and_active_holders():
    assert parse_schedule13(G) == {"filer": 1422849, "issuer": 723125, "name": "Capital World Investors",
                                   "percent": 6.2, "shares": 42208309, "activist": False}
    active = parse_schedule13(D)
    assert (active["name"], active["percent"], active["activist"]) == ("Starboard Value LP", 13.4, True)


SUBMISSIONS = {"filings": {"recent": {
    "form": ["SCHEDULE 13G/A", "8-K", "SCHEDULE 13D", "SCHEDULE 13G", "SC 13G"],
    "filingDate": ["2026-05-14", "2026-05-01", "2026-09-11", "2025-06-01", "2023-01-01"],
    "accessionNumber": ["0001-26-1", "0002-26-1", "0003-26-1", "0001-25-1", "0004-23-1"],
    "primaryDocument": ["xslSCHEDULE_13G_X02/primary_doc.xml", "a.htm", "xslSCHEDULE_13D_X02/primary_doc.xml",
                        "xslSCHEDULE_13G_X01/primary_doc.xml", "x.txt"],
}}}


class FakeClient:
    def __init__(self):
        self.calls = []

    def get_text(self, url, **kwargs):
        self.calls.append(url)
        return {
            "https://www.sec.gov/Archives/edgar/data/723125/0001261/primary_doc.xml": G,
            "https://www.sec.gov/Archives/edgar/data/723125/0003261/primary_doc.xml": D,
            "https://www.sec.gov/Archives/edgar/data/723125/0001251/primary_doc.xml": G.replace("6.2", "5.2"),
        }.get(url)


def test_latest_filing_per_holder_wins_and_cache_saves_requests(tmp_path):
    cache = HolderCache(tmp_path / "holders.json")
    client = FakeClient()
    holders = holders_for(client, 723125, SUBMISSIONS, cache, date(2026, 10, 6), Budget(10))
    assert holders == [
        {"name": "Starboard Value LP", "percent": 13.4, "date": "2026-09-11", "activist": True},
        {"name": "Capital World Investors", "percent": 6.2, "date": "2026-05-14", "activist": False},
    ]
    assert len(client.calls) == 3  # old-format filings from 2023 are out of range
    cache.save()

    again = FakeClient()
    assert holders_for(again, 723125, SUBMISSIONS, HolderCache(tmp_path / "holders.json"), date(2026, 10, 6), Budget(0)) == holders
    assert again.calls == []


def test_without_budget_uncached_filings_wait(tmp_path):
    holders = holders_for(FakeClient(), 723125, SUBMISSIONS, HolderCache(tmp_path / "h.json"), date(2026, 10, 6), Budget(1))
    assert len(holders) == 1


def test_stakes_in_other_companies_and_small_stakes_are_left_out(tmp_path):
    class Client(FakeClient):
        def get_text(self, url, **kwargs):
            if "0003261" in url:
                return D.replace("0000723125", "0000999999")  # the company reporting its stake elsewhere
            if "0001261" in url:
                return G.replace("6.2", "0.0")  # sold down below 5 %
            return super().get_text(url)

    holders = holders_for(Client(), 723125, SUBMISSIONS, HolderCache(tmp_path / "h.json"), date(2026, 10, 6), Budget(10))
    assert holders == []
