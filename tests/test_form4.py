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
    assert _person_name("O'BRIEN DEIRDRE") == "Deirdre O'Brien"
    assert _person_name("SMITH-JONES ANN") == "Ann Smith-Jones"


def test_abbreviated_titles_are_recognised():
    xml = XML.replace("Chief Executive Officer", "EVP and CFO")
    assert parse_form4(xml).role == "CFO"


SALE_XML = XML.replace("<transactionCode>P</transactionCode>", "<transactionCode>S</transactionCode>").replace(
    "<transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>\n   </transactionAmounts>\n  </nonDerivativeTransaction>\n  <nonDerivativeTransaction>",
    "<transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>\n   </transactionAmounts>\n"
    "   <postTransactionAmounts><sharesOwnedFollowingTransaction><value>79500</value></sharesOwnedFollowingTransaction></postTransactionAmounts>\n"
    "  </nonDerivativeTransaction>\n  <nonDerivativeTransaction>",
).replace("<issuer>", "<aff10b5One>1</aff10b5One><issuer>")


def test_collects_purchases_and_sales_as_transactions():
    buy = parse_form4(XML).transactions
    assert [(t.code, t.shares, t.price) for t in buy] == [("P", 20500, 23.40)]
    assert buy[0].planned is False

    sale = parse_form4(SALE_XML)
    assert sale.purchases == []
    assert [(t.code, t.shares, t.shares_after, t.planned) for t in sale.transactions] == [("S", 20500, 79500, True)]


def test_display_role_covers_large_holders():
    xml = XML.replace("<isOfficer>1</isOfficer>", "<isOfficer>0</isOfficer><isTenPercentOwner>1</isTenPercentOwner>")
    filing = parse_form4(xml)
    assert filing.role is None
    assert filing.display_role == "Großaktionär"


def test_company_names_are_not_turned_around():
    from quarry.form4 import _person_name
    assert _person_name("VANGUARD GROUP INC") == "Vanguard Group Inc"
    assert _person_name("Starboard Value LP") == "Starboard Value LP"
    assert _person_name("BAKER BROS. ADVISORS LP") == "Baker Bros. Advisors LP"


def test_principal_officer_titles():
    from quarry.form4 import officer_title, tidy_role
    assert officer_title("PFO and PAO") == "CFO"
    assert officer_title("Chief Accounting Officer") == "CAO"
    assert officer_title("EVP, General Counsel & Secretary") == "Chefjurist"
    assert tidy_role("PFO and PAO") == "CFO"
    assert tidy_role("Direktor") == "Direktor"
