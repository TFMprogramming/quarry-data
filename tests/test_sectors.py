from quarry.sectors import german_sector


def test_specific_codes_win_over_broad_ranges():
    assert german_sector("3674") == "Halbleiter"           # Nvidia, Micron
    assert german_sector("3571") == "Hardware"              # Apple
    assert german_sector("7372") == "Software & Internet"   # Microsoft
    assert german_sector("2834") == "Pharma & Biotech"
    assert german_sector("1311") == "Öl & Gas"
    assert german_sector("6022") == "Banken"
    assert german_sector("5734") == "Einzelhandel"          # GameStop


def test_broad_ranges():
    assert german_sector("3560") == "Industrie & Maschinenbau"
    assert german_sector("4911") == "Versorger"
    assert german_sector("6770") == "Mantelgesellschaften"


def test_unknown_or_missing_code():
    assert german_sector(None) == "Sonstige"
    assert german_sector("") == "Sonstige"
    assert german_sector("abc") == "Sonstige"
