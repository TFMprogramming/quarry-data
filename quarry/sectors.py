"""German sector names from SEC SIC codes.

The SEC uses roughly 400 four-digit SIC codes. They are grouped here into
about two dozen sectors a private investor recognises. Specific codes are
listed first and win over the broad ranges below them."""
from __future__ import annotations

OTHER = "Sonstige"

# (first code, last code, sector) – checked top to bottom, first match wins.
SECTOR_RANGES: list[tuple[int, int, str]] = [
    # Specific codes and small ranges
    (1311, 1311, "Öl & Gas"),
    (1381, 1389, "Öl & Gas"),
    (2911, 2911, "Öl & Gas"),
    (4922, 4925, "Öl & Gas"),
    (5171, 5172, "Öl & Gas"),
    (2830, 2836, "Pharma & Biotech"),
    (3674, 3674, "Halbleiter"),
    (3570, 3579, "Hardware"),
    (3660, 3679, "Elektronik"),
    (3710, 3716, "Automobil"),
    (3720, 3729, "Luft- & Raumfahrt"),
    (3760, 3769, "Luft- & Raumfahrt"),
    (3840, 3851, "Medizintechnik"),
    (7370, 7379, "Software & Internet"),
    (7800, 7999, "Medien & Unterhaltung"),
    (6770, 6770, "Mantelgesellschaften"),
    (6798, 6798, "Immobilien"),
    (8000, 8099, "Gesundheitswesen"),
    # Broad ranges
    (100, 999, "Landwirtschaft"),
    (1000, 1499, "Rohstoffe & Bergbau"),
    (1500, 1799, "Bau"),
    (2000, 2199, "Lebensmittel & Getränke"),
    (2200, 2399, "Konsumgüter"),
    (2400, 2799, "Materialien"),
    (2800, 2899, "Chemie"),
    (2900, 3099, "Materialien"),
    (3100, 3199, "Konsumgüter"),
    (3200, 3399, "Materialien"),
    (3600, 3699, "Elektronik"),
    (3000, 3999, "Industrie & Maschinenbau"),
    (4000, 4799, "Transport & Logistik"),
    (4800, 4899, "Telekommunikation & Medien"),
    (4900, 4999, "Versorger"),
    (5000, 5199, "Großhandel"),
    (5200, 5999, "Einzelhandel"),
    (6000, 6199, "Banken"),
    (6200, 6299, "Finanzdienstleistungen"),
    (6300, 6499, "Versicherungen"),
    (6500, 6599, "Immobilien"),
    (6700, 6799, "Beteiligungen & Fonds"),
    (7000, 7999, "Dienstleistungen"),
    (8100, 8999, "Dienstleistungen"),
]


def german_sector(sic: str | None) -> str:
    try:
        code = int(sic or "")
    except ValueError:
        return OTHER
    for first, last, sector in SECTOR_RANGES:
        if first <= code <= last:
            return sector
    return OTHER
