"""Population-profile drift: one period's composition against a baseline
window's, with the uncertainty attached.

What a finding means, precisely: the share of some category (a preparer, a
source) inside a monitoring period differs from that category's share
across the baseline periods by more than a stated materiality floor, and
the two Wilson intervals do not overlap. Both conditions are required, for
the reason DECISIONS D-016 gives about chi-square: significance alone grows
with n, so a large enough population makes every trivial wobble
"significant". The floor states how much change is worth an auditor's
morning; the intervals state whether the data can support the claim that it
changed at all. Neither alone is a finding.

Intervals belong here even though the counts are exact (D-023 draws that
line carefully). A period's composition is not a sample of a bigger set of
entries — it is every entry in the period. The inference is about the
*process* that produced the population: could the same posting behaviour
that generated the baseline plausibly have produced this month? That is the
same framing under which Benford digit proportions carry intervals.

Directionality is asymmetric on purpose. An *increase* in a category's
share names the entries a reviewer can open — the cell's entries — so it
carries entry-level leads. A *decrease* names no entries at all: the drift
is in what is absent, and pointing at the survivors would be nonsense. A
decrease is reported as a finding with no entry ids, never dropped.

Determinism: every iteration is over sorted keys; the report contains no
wall-clock timestamps (D-007/D-019).
"""

from dataclasses import dataclass

from analytics.profile import PopulationProfile
from continuous.periods import monthly_batches, combine_batches, split_baseline
from core.stats import DEFAULT_CONFIDENCE, Measurement, proportion

# Dimensions this screen supports. by_account is deliberately excluded: the
# profile counts it per *line*, so its shares have a different denominator
# than the entry membership a lead would point at (analytics.profile
# documents the split). by_month would compare a period against itself.
SUPPORTED_DIMENSIONS = ("by_preparer", "by_source", "by_weekday")
DEFAULT_DIMENSIONS = ("by_preparer", "by_source")

# category-of-an-entry, matching each profile tally exactly.
_ENTRY_CATEGORY = {
    "by_preparer": lambda e: e.preparer_id,
    "by_source": lambda e: e.source,
    "by_weekday": lambda e: str(e.posting_date.weekday()),
}

INCREASE = "increase"
DECREASE = "decrease"


def intervals_disjoint(a: tuple, b: tuple) -> bool:
    """True when two closed intervals share no point.

    Non-overlap is a conservative comparison — deliberately more demanding
    than testing whether one interval contains the other's point estimate,
    because the baseline is itself measured, not given.
    """
    return a[1] < b[0] or b[1] < a[0]


@dataclass(frozen=True)
class DriftParams:
    """Screen parameters. These are engagement choices, not standards, and
    they are echoed into every report and workpaper that shows a finding.

    `min_shift` is the materiality floor in absolute share points. Its
    default is calibrated against measured clean-population behaviour
    (DECISIONS D-028), not chosen for looks: below it, ordinary
    month-to-month variation in a modest ledger clears the interval test.
    """

    baseline_periods: int = 3
    dimensions: tuple = DEFAULT_DIMENSIONS
    min_shift: float = 0.15
    min_period_entries: int = 30
    min_baseline_entries: int = 100
    min_category_baseline: int = 10
    confidence: float = DEFAULT_CONFIDENCE

    def __post_init__(self):
        if self.baseline_periods < 1:
            raise ValueError("baseline_periods must be at least 1")
        if not 0.0 < self.min_shift < 1.0:
            raise ValueError("min_shift must be in (0, 1)")
        if not self.dimensions:
            raise ValueError("at least one dimension is required")
        for d in self.dimensions:
            if d not in SUPPORTED_DIMENSIONS:
                raise ValueError(
                    f"unsupported drift dimension {d!r}; supported: "
                    f"{', '.join(SUPPORTED_DIMENSIONS)}"
                )

    def to_dict(self) -> dict:
        return {
            "baseline_periods": self.baseline_periods,
            "dimensions": list(self.dimensions),
            "min_shift": self.min_shift,
            "min_period_entries": self.min_period_entries,
            "min_baseline_entries": self.min_baseline_entries,
            "min_category_baseline": self.min_category_baseline,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class DriftFinding:
    """One (period, dimension, category) cell whose share moved."""

    period: str
    dimension: str
    category: str
    direction: str
    shift: float                 # period share minus baseline share
    baseline_share: Measurement
    period_share: Measurement
    entry_ids: tuple             # the cell's entries; empty for a decrease

    @property
    def statement(self) -> str:
        """One rendered sentence, sample sizes included (D-023's line rule
        applies to anything that reaches a document)."""
        return (
            f"{self.dimension.replace('by_', '')} {self.category} moved from "
            f"{self.baseline_share.numerator}/{self.baseline_share.n} of the "
            f"baseline to {self.period_share.numerator}/{self.period_share.n} "
            f"of {self.period} ({self.direction} of {abs(self.shift):.3f} "
            f"share points; baseline {self.baseline_share.render()}, period "
            f"{self.period_share.render()})"
        )

    def to_dict(self) -> dict:
        return {
            "period": self.period,
            "dimension": self.dimension,
            "category": self.category,
            "direction": self.direction,
            "shift": round(self.shift, 6),
            "baseline_share": self.baseline_share.to_dict(),
            "period_share": self.period_share.to_dict(),
            "n_cell_entries": len(self.entry_ids),
            "entry_ids": list(self.entry_ids),
            "statement": self.statement,
        }


@dataclass(frozen=True)
class UntestedPeriod:
    """A period the screen refused to test, and why. Refusals are scope
    limitations, never quiet passes (D-011)."""

    period: str
    n_entries: int
    reason: str

    def to_dict(self) -> dict:
        return {
            "period": self.period,
            "n_entries": self.n_entries,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class DriftReport:
    params: DriftParams
    baseline_periods: tuple
    baseline_n_entries: int
    tested_periods: tuple
    findings: tuple
    untested: tuple
    applicable: bool = True
    refusal_reason: str = ""

    def flagged_entry_ids(self) -> tuple:
        out = set()
        for f in self.findings:
            out |= set(f.entry_ids)
        return tuple(sorted(out))

    def findings_for(self, period: str) -> tuple:
        return tuple(f for f in self.findings if f.period == period)

    def to_dict(self) -> dict:
        return {
            "applicable": self.applicable,
            "refusal_reason": self.refusal_reason,
            "params": self.params.to_dict(),
            "period_basis": "posting_date",
            "baseline_periods": list(self.baseline_periods),
            "baseline_n_entries": self.baseline_n_entries,
            "tested_periods": list(self.tested_periods),
            "n_findings": len(self.findings),
            "findings": [f.to_dict() for f in self.findings],
            "untested_periods": [u.to_dict() for u in self.untested],
        }


def compare_profiles(
    baseline_profile: PopulationProfile,
    period_profile: PopulationProfile,
    dimension: str,
    period: str,
    params: DriftParams = DriftParams(),
    entries=(),
) -> list:
    """Findings for one dimension of one period against one baseline.

    `entries` are the period's entries, used only to name the cell members
    of an increase; the statistics come from the two profiles alone, so this
    function is testable against hand-built profiles.
    """
    if dimension not in SUPPORTED_DIMENSIONS:
        raise ValueError(f"unsupported drift dimension: {dimension!r}")
    base_counts = baseline_profile.dimension(dimension)
    period_counts = period_profile.dimension(dimension)
    base_n = baseline_profile.dimension_total(dimension)
    period_n = period_profile.dimension_total(dimension)
    if base_n == 0 or period_n == 0:
        return []

    category_of = _ENTRY_CATEGORY[dimension]
    findings = []
    for category in sorted(set(base_counts) | set(period_counts)):
        base_k = base_counts.get(category, 0)
        period_k = period_counts.get(category, 0)
        # A category that barely exists in the baseline has no stable share
        # to drift from; excluding it is a stated limitation, not an
        # oversight — the screen cannot see a rare category becoming
        # slightly less rare, and says so.
        if base_k < params.min_category_baseline:
            continue
        base_share = proportion(
            f"baseline share[{dimension}:{category}]", base_k, base_n,
            confidence=params.confidence,
        )
        period_share = proportion(
            f"{period} share[{dimension}:{category}]",
            period_k, period_n, confidence=params.confidence,
        )
        shift = period_share.value - base_share.value
        if abs(shift) < params.min_shift:
            continue
        if not intervals_disjoint(base_share.interval, period_share.interval):
            continue
        direction = INCREASE if shift > 0 else DECREASE
        cell_ids = ()
        if direction == INCREASE:
            cell_ids = tuple(
                sorted(e.entry_id for e in entries if category_of(e) == category)
            )
        findings.append(
            DriftFinding(
                period=period,
                dimension=dimension,
                category=category,
                direction=direction,
                shift=shift,
                baseline_share=base_share,
                period_share=period_share,
                entry_ids=cell_ids,
            )
        )
    return findings


def analyze(ledger, params: DriftParams = DriftParams()) -> DriftReport:
    """Batch a ledger by month and compare every post-baseline period to the
    baseline window.

    Refuses (applicable=False) rather than opining when the ledger cannot
    support the comparison: too few periods to have both a baseline and a
    tested period, or a baseline window too thin to give the comparison any
    resolution. A refusal renders as inconclusive (D-011); it never renders
    as "no drift".
    """
    batches = monthly_batches(ledger)
    if len(batches) <= params.baseline_periods:
        return DriftReport(
            params=params,
            baseline_periods=tuple(b.period for b in batches),
            baseline_n_entries=sum(len(b) for b in batches),
            tested_periods=(),
            findings=(),
            untested=(),
            applicable=False,
            refusal_reason=(
                f"{len(batches)} monthly batch(es) present; a baseline of "
                f"{params.baseline_periods} plus at least one tested period "
                f"is required"
            ),
        )

    baseline, tested = split_baseline(batches, params.baseline_periods)
    baseline_ledger = combine_batches(ledger, baseline)
    baseline_profile = PopulationProfile.build(baseline_ledger)
    baseline_n = len(baseline_ledger)
    if baseline_n < params.min_baseline_entries:
        return DriftReport(
            params=params,
            baseline_periods=tuple(b.period for b in baseline),
            baseline_n_entries=baseline_n,
            tested_periods=(),
            findings=(),
            untested=(),
            applicable=False,
            refusal_reason=(
                f"baseline window holds {baseline_n} entries, below the "
                f"minimum of {params.min_baseline_entries}; a share measured "
                f"on that base cannot resolve a drift of "
                f"{params.min_shift:.2f}"
            ),
        )

    findings = []
    untested = []
    tested_periods = []
    for batch in tested:
        if len(batch) < params.min_period_entries:
            untested.append(
                UntestedPeriod(
                    period=batch.period,
                    n_entries=len(batch),
                    reason=(
                        f"{len(batch)} entries is below the minimum of "
                        f"{params.min_period_entries} for a share comparison"
                    ),
                )
            )
            continue
        tested_periods.append(batch.period)
        period_profile = batch.profile()
        for dimension in params.dimensions:
            findings.extend(
                compare_profiles(
                    baseline_profile,
                    period_profile,
                    dimension,
                    batch.period,
                    params,
                    entries=batch.ledger.entries,
                )
            )

    findings.sort(key=lambda f: (f.period, f.dimension, f.category))
    return DriftReport(
        params=params,
        baseline_periods=tuple(b.period for b in baseline),
        baseline_n_entries=baseline_n,
        tested_periods=tuple(tested_periods),
        findings=tuple(findings),
        untested=tuple(untested),
    )
