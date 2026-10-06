"""Everything a company profile needs beyond its own SEC files: the insider
history and the large-shareholder filings, both shared across companies."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from quarry.budget import Budget
from quarry.holders import HolderCache, holders_for
from quarry.valuation import ValuationContext


@dataclass
class CompanyExtras:
    insiders: dict[int, list[dict]] = field(default_factory=dict)
    insider_since: date | None = None
    holder_cache: HolderCache | None = None
    holder_budget: Budget = field(default_factory=lambda: Budget(0))
    valuation: ValuationContext | None = None

    def for_company(self, client, cik: int, submissions: dict, today: date) -> dict:
        """Keyword arguments for `build_company`."""
        holders = None
        if self.holder_cache is not None:
            holders = holders_for(client, cik, submissions, self.holder_cache, today, self.holder_budget)
        return {
            "insider_records": self.insiders.get(cik, []),
            "insider_since": self.insider_since,
            "holders": holders,
            "holder_filings": self.holder_cache.entries if self.holder_cache else {},
            "valuation_context": self.valuation,
        }
