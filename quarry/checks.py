""""At a glance": plain facts about a company's financial health, good and bad.
They describe, they don't judge – no buy or sell hints."""
from __future__ import annotations

from quarry.facts import Quarter
from quarry.formatting import money

DILUTION_WARNING = 0.10
DILUTION_NOTE = 0.03
BUYBACK = -0.02


def health_checks(quarters: list[Quarter], balance: dict | None, events: list[dict]) -> list[dict]:
    checks = [
        _profit(quarters),
        _cash(balance or {}),
        _shares(balance or {}),
        *[_check("warning", event["title"], f"Gemeldet am {_german_date(event['date'])}.")
          for event in events if event["kind"] == "warning"],
        _debt(balance or {}),
    ]
    unique: dict[str, dict] = {}
    for check in checks:
        if check and check["title"] not in unique:  # the newest of repeated warnings
            unique[check["title"]] = check
    checks = list(unique.values())
    order = {"warning": 0, "info": 1, "ok": 2}
    return sorted(checks, key=lambda check: order[check["level"]])


def _profit(quarters: list[Quarter]) -> dict | None:
    incomes = [q.net_income for q in quarters[-4:] if q.net_income is not None]
    if len(incomes) < 3:
        return None
    total = sum(incomes)
    span = f"in den letzten {len(incomes)} Quartalen"
    if total < 0:
        return _check("warning", "Macht Verluste", f"Verlust von {money(-total)} {span}.")
    return _check("ok", "Profitabel", f"Gewinn von {money(total)} {span}.")


def _cash(balance: dict) -> dict | None:
    cash, flow = balance.get("cash"), balance.get("freeCashFlow")
    if flow is None:
        return None
    if flow >= 0:
        return _check("ok", "Erwirtschaftet Geld", f"Free Cashflow von {money(flow)} in zwölf Monaten.")
    if cash is None:
        return _check("warning", "Verbraucht Geld", f"Abfluss von {money(-flow)} in zwölf Monaten.")
    months = cash / (-flow / 12)
    detail = (f"Kasse {money(cash)}, Abfluss {money(-flow)} in zwölf Monaten. "
              "Danach bräuchte die Firma neues Geld – oft über neue Aktien.")
    if months < 24:
        return _check("warning" if months < 12 else "info", f"Geld reicht rechnerisch etwa {round(months)} Monate", detail)
    return _check("info", "Geld reicht rechnerisch über zwei Jahre", detail)


def _shares(balance: dict) -> dict | None:
    change = balance.get("sharesChange")
    if change is None:
        return None
    text = f"{'+' if change >= 0 else '−'}{abs(change) * 100:.0f} %"
    if change >= DILUTION_WARNING:
        return _check("warning", f"Aktienzahl {text} in einem Jahr",
                      "Neue Aktien verkleinern den Anteil bestehender Aktionäre (Verwässerung).")
    if change >= DILUTION_NOTE:
        return _check("info", f"Aktienzahl {text} in einem Jahr", "Leichte Verwässerung, z. B. durch Mitarbeiteraktien.")
    if change <= BUYBACK:
        return _check("ok", "Kauft eigene Aktien zurück", f"Aktienzahl {text} in einem Jahr.")
    return None


def _debt(balance: dict) -> dict | None:
    cash, debt = balance.get("cash"), balance.get("debt")
    if cash is None:
        return None
    if not debt:
        return _check("ok", "Keine Finanzschulden", f"Kasse {money(cash)}.")
    if debt > cash:
        return _check("info", "Mehr Schulden als Geld", f"Schulden {money(debt)}, Kasse {money(cash)}.")
    return _check("ok", "Mehr Geld als Schulden", f"Kasse {money(cash)}, Schulden {money(debt)}.")


def _check(level: str, title: str, detail: str) -> dict:
    return {"level": level, "title": title, "detail": detail}


def _german_date(iso: str) -> str:
    year, month, day = iso.split("-")
    return f"{int(day)}.{int(month)}.{year}"
