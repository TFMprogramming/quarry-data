# quarry-data

Tägliche Datenpipeline für die Quarry-App. Ein GitHub-Job liest jeden Morgen die
Meldungen des Vortags bei der SEC (Insider-Käufe aus Form 4, Umsatzwachstum aus
10-Q/10-K), berechnet die Signale und veröffentlicht `feed.json` über GitHub Pages.

- Nur öffentliche SEC-Daten, keine Kursdaten.
- `data/events/` speichert jeden verarbeiteten Tag (90 Tage Historie für das Insider-Signal).
- Lokal: `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`,
  Tests mit `.venv/bin/pytest`, Lauf mit `.venv/bin/python -m quarry --days 4`.

Keine Anlageberatung. Daten: U.S. Securities and Exchange Commission (EDGAR).
