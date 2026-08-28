"""Monthly batching: slice one ledger into the periods a monitoring
programme would actually process.

Batching is by **posting date**, not effective date. A continuous monitor
sees an entry when it hits the ledger, and the gap between the two dates is
itself the signal a post-close test looks for (R-002): batching on the
effective date would file a January-posted, December-effective entry into
December and quietly hide the very lag worth seeing. `JournalEntry.period`
remains the effective-date fiscal period — the two are deliberately
different questions, so this module names its basis explicitly rather than
reusing that property (DECISIONS D-027).

Batches are sub-ledgers, not a new type: the same `Ledger` with a subset of
entries and the parent's chart, users and metadata. That is what lets any
existing rule, the profiler, and the report card operate on a batch with no
special-casing — a batch is just a smaller population.
"""

from dataclasses import dataclass

from analytics.profile import PopulationProfile
from core.dates import period_str
from ledger.model import Ledger

PERIOD_BASIS = "posting_date"


def period_of(entry) -> str:
    """The monitoring period an entry belongs to: 'YYYY-MM' of its posting
    date (see the module docstring for why not the effective date)."""
    return period_str(entry.posting_date)


def sub_ledger(ledger, entries, period_label: str = "") -> Ledger:
    """A ledger over `entries` carrying the parent's chart, users and meta.

    Meta is copied (not shared) and annotated with the slice, so a workpaper
    rendered from a batch cannot silently claim the parent's entry count.
    """
    meta = dict(ledger.meta)
    meta["n_entries"] = len(entries)
    meta["batch"] = {
        "period": period_label,
        "period_basis": PERIOD_BASIS,
        "parent_n_entries": len(ledger),
    }
    return Ledger(coa=ledger.coa, users=ledger.users, entries=tuple(entries), meta=meta)


@dataclass(frozen=True)
class PeriodBatch:
    """One monitoring period's population."""

    period: str
    ledger: Ledger

    def __len__(self) -> int:
        return len(self.ledger)

    def profile(self) -> PopulationProfile:
        """The batch's population profile — the object drift diffs."""
        return PopulationProfile.build(self.ledger)

    def to_dict(self) -> dict:
        return {"period": self.period, "n_entries": len(self.ledger)}


def monthly_batches(ledger) -> tuple:
    """Split into `PeriodBatch`es, ascending by period label.

    Entry order inside a batch is the parent's order (already
    posting-date/rank ordered by the generator), so batching is a pure
    partition: concatenating the batches in period order reproduces the
    parent's entry sequence exactly.
    """
    grouped = {}
    for e in ledger.entries:
        grouped.setdefault(period_of(e), []).append(e)
    return tuple(
        PeriodBatch(period=p, ledger=sub_ledger(ledger, grouped[p], p))
        for p in sorted(grouped)
    )


def combine_batches(ledger, batches, period_label: str = "") -> Ledger:
    """One sub-ledger spanning several batches — how a baseline window of
    consecutive periods is profiled as a single population."""
    entries = []
    for b in batches:
        entries.extend(b.ledger.entries)
    label = period_label or (
        f"{batches[0].period}..{batches[-1].period}" if batches else ""
    )
    return sub_ledger(ledger, entries, label)


def split_baseline(batches, n_baseline: int):
    """(baseline batches, tested batches) — the first `n_baseline` periods
    are the comparison base and are never themselves tested against it.

    Drift planted inside the baseline window would poison the base it is
    measured against; keeping the split explicit (rather than a rolling
    window) is what makes "versus a baseline period" a checkable claim.
    """
    if n_baseline < 1:
        raise ValueError("n_baseline must be at least 1")
    return tuple(batches[:n_baseline]), tuple(batches[n_baseline:])
