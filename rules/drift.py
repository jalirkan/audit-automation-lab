"""The continuous-mode rule: population-profile drift as a JE test.

R-012 is a rule in the same sense the other eleven are — declared
population, stated criterion, per-entry rationale, refusal when its
preconditions fail — but it concludes about a *cell*, not an entry. When a
preparer's share of a month moves, the lead is "look at this preparer's
postings in this month"; the rule names those entries because that is what a
reviewer opens, and a reviewer opening them will find that most were always
that preparer's to post.

That ceiling is deliberate and measured, not hidden: entry-level precision
for this screen cannot exceed the drifted cell's planted fraction, and the
report card prints whatever it actually is (DECISIONS D-029). A screen whose
precision looked like a duplicate test's would mean the plant, not the
screen, was doing the work.

The rule is not in the default battery. It needs several monthly batches and
a baseline window, which a single-period extract does not have, and it
targets drift classes no point-in-time rule covers; keeping it in its own
battery is the same scoping honesty as R-003's excluded sources
(DECISIONS D-030).
"""

from continuous.drift import DriftParams, analyze
from continuous.periods import period_of
from rules.base import Flag, Rule, sort_flags


class ProfileDriftRule(Rule):
    rule_id = "R-012"
    title = "Population-profile drift against a baseline period"
    targets = ("preparer_concentration_drift", "manual_source_surge")
    references = ("AU-C 240",)
    population_description = (
        "All journal entries, batched by posting month; the first baseline "
        "periods define the comparison base and are not themselves tested."
    )
    criterion_description = (
        "Within a monthly batch, a category's share of a composition "
        "dimension (preparer, source) differs from its share across the "
        "baseline periods by at least the materiality floor AND the two "
        "Wilson intervals do not overlap. Entries are flagged for share "
        "increases only — a decrease is reported as a finding but names no "
        "entries, because the drift is in what is absent."
    )
    limitations = (
        "The screen concludes about a period-and-category cell, not about an "
        "entry: every entry in a drifted cell is named as a lead, including "
        "the ones that were always there, so entry-level precision is capped "
        "by the cell's composition.",
        "A materiality floor stated in absolute share points cannot see a "
        "small category becoming a slightly larger small one; at monthly "
        "volumes such a move is indistinguishable from ordinary variation.",
        "The baseline is assumed to be a period of normal operation. Drift "
        "planted inside the baseline window moves the base it would be "
        "measured against, and this screen cannot detect it.",
        "Seasonality is not modelled: a dimension that legitimately shifts "
        "with the calendar (weekday mix around month-end) is excluded from "
        "the defaults, and including it is an auditor scoping decision "
        "recorded in parameters.",
    )

    def __init__(self, drift_params: DriftParams = None):
        self.drift_params = drift_params or DriftParams()
        # evaluate_all asks each rule for applicability, population size and
        # flags in turn; drift analysis is the expensive part of all three,
        # so the last report is memoised against the ledger it was built
        # from. The reference is held so the identity check cannot be fooled
        # by a recycled id.
        self._cache = None

    def params(self) -> dict:
        return self.drift_params.to_dict()

    def analyze(self, ledger):
        """The full drift report — findings, refusals and untested periods.

        Rules return flags; a monitoring programme also needs the findings
        that produced no entry-level leads (share decreases) and the periods
        that could not be tested at all. Those reach the workpaper through
        here rather than being discarded at the flag boundary.
        """
        if self._cache is not None and self._cache[0] is ledger:
            return self._cache[1]
        report = analyze(ledger, self.drift_params)
        self._cache = (ledger, report)
        return report

    def applicable(self, ledger):
        report = self.analyze(ledger)
        if not report.applicable:
            return False, report.refusal_reason
        return True, ""

    def population(self, ledger):
        """Entries in the tested (post-baseline) periods: the baseline
        window is the comparison base, not a population under test."""
        report = self.analyze(ledger)
        if not report.applicable:
            return []
        tested = set(report.tested_periods)
        return [e for e in ledger.entries if period_of(e) in tested]

    def evaluate(self, ledger):
        report = self.analyze(ledger)
        flags = []
        for finding in report.findings:
            for entry_id in finding.entry_ids:
                flags.append(
                    Flag(
                        self.rule_id,
                        entry_id,
                        f"In {finding.period}, this entry sits in a drifted "
                        f"cell: {finding.statement}",
                        {
                            "period": finding.period,
                            "dimension": finding.dimension,
                            "category": finding.category,
                            "direction": finding.direction,
                            "shift": round(finding.shift, 6),
                        },
                    )
                )
        return sort_flags(flags)
