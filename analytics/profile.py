"""Population profiling: deterministic descriptive structure of a ledger.

This is the baseline object the stretch-phase drift comparison would diff;
in v1 it feeds the workpapers' population sections. Quantiles use the
nearest-rank method on the (n-1) index scale — pinned here so two runs (and
two platforms) produce identical integers, with no interpolation floats.
"""

from dataclasses import dataclass

from core.dates import period_str


def nearest_rank_deciles(sorted_values):
    """{0: min, 1: d1, ..., 10: max} via index round(q*(n-1)/10)."""
    n = len(sorted_values)
    if n == 0:
        return {}
    out = {}
    for q in range(0, 11):
        idx = round(q * (n - 1) / 10)
        out[q] = sorted_values[idx]
    return out


@dataclass(frozen=True)
class PopulationProfile:
    n_entries: int
    n_lines: int
    date_min: str
    date_max: str
    total_amount_cents: int
    by_weekday: dict
    by_month: dict
    by_source: dict
    by_preparer: dict
    by_account: dict
    amount_deciles: dict
    n_requiring_approval: int
    n_missing_approval: int
    top_amounts: tuple

    @staticmethod
    def build(ledger) -> "PopulationProfile":
        threshold = ledger.meta.get("approval_threshold_cents")
        by_weekday = {d: 0 for d in range(7)}
        by_month = {}
        by_source = {}
        by_preparer = {}
        by_account = {}
        amounts = []
        n_lines = 0
        requiring = 0
        missing = 0
        for e in ledger.entries:
            by_weekday[e.posting_date.weekday()] += 1
            month = period_str(e.posting_date)
            by_month[month] = by_month.get(month, 0) + 1
            by_source[e.source] = by_source.get(e.source, 0) + 1
            by_preparer[e.preparer_id] = by_preparer.get(e.preparer_id, 0) + 1
            for line in e.lines:
                n_lines += 1
                by_account[line.account_id] = by_account.get(line.account_id, 0) + 1
            amounts.append(e.amount_cents)
            if threshold is not None and (
                e.source == "GL" or e.amount_cents >= threshold
            ):
                requiring += 1
                if e.approver_id is None:
                    missing += 1
        ranked = sorted(
            ledger.entries, key=lambda e: (-e.amount_cents, e.entry_id)
        )[:5]
        return PopulationProfile(
            n_entries=len(ledger.entries),
            n_lines=n_lines,
            date_min=min(e.posting_date for e in ledger.entries).isoformat()
            if ledger.entries
            else "",
            date_max=max(e.posting_date for e in ledger.entries).isoformat()
            if ledger.entries
            else "",
            total_amount_cents=sum(amounts),
            by_weekday=by_weekday,
            by_month=dict(sorted(by_month.items())),
            by_source=dict(sorted(by_source.items())),
            by_preparer=dict(sorted(by_preparer.items())),
            by_account=dict(sorted(by_account.items())),
            amount_deciles=nearest_rank_deciles(sorted(amounts)),
            n_requiring_approval=requiring,
            n_missing_approval=missing,
            top_amounts=tuple(
                {"entry_id": e.entry_id, "amount_cents": e.amount_cents}
                for e in ranked
            ),
        )

    def to_dict(self) -> dict:
        return {
            "n_entries": self.n_entries,
            "n_lines": self.n_lines,
            "date_min": self.date_min,
            "date_max": self.date_max,
            "total_amount_cents": self.total_amount_cents,
            "by_weekday": {str(k): v for k, v in self.by_weekday.items()},
            "by_month": self.by_month,
            "by_source": self.by_source,
            "by_preparer": self.by_preparer,
            "by_account": self.by_account,
            "amount_deciles": {str(k): v for k, v in self.amount_deciles.items()},
            "n_requiring_approval": self.n_requiring_approval,
            "n_missing_approval": self.n_missing_approval,
            "top_amounts": list(self.top_amounts),
        }
