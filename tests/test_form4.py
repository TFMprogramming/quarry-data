from datetime import date

from quarry.form4 import extract_ownership_xml, parse_form4

XML = """<ownershipDocument>
 <issuer><issuerCik>0000108312</issuerCik><issuerName>Woodward, Inc.</issuerName><issuerTradingSymbol>WWD</issuerTradingSymbol></issuer>
 <reportingOwner>
  <reportingOwnerId><rptOwnerName>OLSEN MARGARET</rptOwnerName></reportingOwnerId>
  <reportingOwnerRelationship><isDirector>0</isDirector><isOfficer>1</isOfficer><officerTitle>Chief Executive Officer</officerTitle></reportingOwnerRelationship>
 </reportingOwner>
 <nonDerivativeTable>
  <nonDerivativeTransaction>
   <transactionDate><value>2026-10-01</value></transactionDate>
   <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
   <transactionAmounts>
    <transactionShares><value>20500</value></transactionShares>
    <transactionPricePerShare><value>23.40</value></transactionPricePerShare>
    <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
   </transactionAmounts>
  </nonDerivativeTransaction>
  <nonDerivativeTransaction>
   <transactionDate><value>2026-10-01</value></transactionDate>
   <transactionCoding><transactionCode>A</transactionCode></transactionCoding>
   <transactionAmounts>
    <transactionShares><value>520</value></transactionShares>
    <transactionPricePerShare><value>0.00</value></transactionPricePerShare>
    <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
   </transactionAmounts>
  </nonDerivativeTransaction>
 </nonDerivativeTable>
</ownershipDocument>"""


def test_extracts_xml_from_full_submission():
    assert extract_ownership_xml("<SEC-DOCUMENT>junk<XML>\n" + XML + "\n</XML>") == XML


def test_parses_only_open_market_purchases():
    filing = parse_form4(XML)
    assert (filing.issuer_cik, filing.ticker, filing.issuer_name) == (108312, "WWD", "Woodward, Inc.")
    assert filing.owner_name == "Margaret Olsen"
    assert filing.role == "CEO"
    assert len(filing.purchases) == 1
    purchase = filing.purchases[0]
    assert purchase.date == date(2026, 10, 1)
    assert purchase.value == 20500 * 23.40


def test_ten_percent_owner_has_no_role():
    xml = XML.replace("<isOfficer>1</isOfficer>", "<isOfficer>0</isOfficer>")
    assert parse_form4(xml).role is None


def test_director_role():
    xml = XML.replace("<isOfficer>1</isOfficer>", "<isOfficer>0</isOfficer>").replace(
        "<isDirector>0</isDirector>", "<isDirector>true</isDirector>"
    )
    assert parse_form4(xml).role == "Direktor"


def test_names_are_turned_around_and_keep_suffixes():
    from quarry.form4 import _person_name
    assert _person_name("Cohen Ryan") == "Ryan Cohen"
    assert _person_name("AULT MILTON C III") == "Milton C Ault III"
    assert _person_name("OLSEN MARGARET") == "Margaret Olsen"


def test_abbreviated_titles_are_recognised():
    xml = XML.replace("Chief Executive Officer", "EVP and CFO")
    assert parse_form4(xml).role == "CFO"
