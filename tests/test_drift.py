import unittest
from datetime import date, timedelta

from analytics.profile import PopulationProfile
from continuous.drift import (
    DEFAULT_DIMENSIONS,
    DriftParams,
    DriftReport,
    analyze,
    compare_profiles,
    intervals_disjoint,
)
from core.canonical import canonical_bytes
from core.stats import proportion, wilson_interval
from ledger.generate import GeneratorConfig, generate
from tests.test_rules import mk_entry, mk_ledger


def mk_population(preparers, start=date(2025, 3, 3), source="AP"):
    """A ledger with one entry per element of `preparers`, on consecutive
    days inside one month, so shares are exactly controllable."""
    entries = []
    for i, preparer in enumerate(preparers, start=1):
        entries.append(
            mk_entry(
                f"JE-{i:06d}",
                start + timedelta(days=i % 25),
                preparer=preparer,
                source=source,
                approver="A-01",
            )
        )
    return mk_ledger(entries)


def profile_of(preparers, **kw):
    return PopulationProfile.build(mk_population(preparers, **kw))


def shares(target_count, total, target="P-01", others=("P-02", "P-03")):
    """`target_count` entries for the drifting preparer, the rest spread
    evenly over the others — spread, because with a single other preparer
    every shift has an exact mirror and the fixture would test two findings
    where it means to test one."""
    out = [target] * target_count
    for i in range(total - target_count):
        out.append(others[i % len(others)])
    return out


class DisjointIntervalTests(unittest.TestCase):
    def test_touching_intervals_are_not_disjoint(self):
        self.assertTrue(intervals_disjoint((0.0, 0.1), (0.2, 0.3)))
        self.assertTrue(intervals_disjoint((0.2, 0.3), (0.0, 0.1)))
        self.assertFalse(intervals_disjoint((0.0, 0.2), (0.2, 0.3)))
        self.assertFalse(intervals_disjoint((0.0, 0.5), (0.1, 0.2)))


class BothGatesRequiredTests(unittest.TestCase):
    """The criterion has two gates and the tests exercise each alone.

    Hand-computed base case: P-01 holds 40 of 200 baseline entries (0.20)
    and 40 of 100 in the period (0.40). The shift is 0.20, above the 0.15
    floor, and the Wilson intervals are disjoint — so it fires.
    """

    def setUp(self):
        self.baseline = profile_of(shares(40, 200))
        self.params = DriftParams()

    def test_fires_when_both_gates_pass(self):
        period = profile_of(shares(40, 100))
        findings = compare_profiles(
            self.baseline, period, "by_preparer", "2025-06", self.params
        )
        self.assertEqual([f.category for f in findings], ["P-01"])
        f = findings[0]
        self.assertEqual(f.direction, "increase")
        self.assertAlmostEqual(f.shift, 0.20, places=9)
        # The measurements are exactly core.stats proportions — no private
        # interval arithmetic hides in this module.
        self.assertEqual(f.baseline_share.interval, proportion("x", 40, 200).interval)
        self.assertEqual(f.period_share.interval, proportion("x", 40, 100).interval)
        self.assertEqual((f.period_share.numerator, f.period_share.n), (40, 100))

    def test_interval_gate_alone_blocks_a_large_but_unsupported_shift(self):
        """20 entries showing 0.40 against a 0.20 baseline is a 0.20 shift —
        over the floor — but 8 observations cannot support it, and the
        overlapping intervals say so."""
        period = profile_of(shares(8, 20))
        self.assertFalse(
            intervals_disjoint(wilson_interval(40, 200), wilson_interval(8, 20))
        )
        findings = compare_profiles(
            self.baseline, period, "by_preparer", "2025-06", self.params
        )
        self.assertEqual(findings, [])

    def test_materiality_gate_alone_blocks_a_significant_trifle(self):
        """The D-016 lesson in drift form: at n=2000 a move from 0.20 to
        0.25 has disjoint intervals and is worth nobody's morning. The floor
        is what stops statistical power from manufacturing findings."""
        big_baseline = profile_of(shares(400, 2000))
        period = profile_of(shares(500, 2000))
        self.assertTrue(
            intervals_disjoint(wilson_interval(400, 2000), wilson_interval(500, 2000))
        )
        findings = compare_profiles(
            big_baseline, period, "by_preparer", "2025-06", self.params
        )
        self.assertEqual(findings, [])
        # Lower the floor below the observed shift and the same data fires:
        # the gate, not the data, was the difference.
        loosened = DriftParams(min_shift=0.04)
        self.assertEqual(
            [f.category for f in compare_profiles(
                big_baseline, period, "by_preparer", "2025-06", loosened)],
            ["P-01"],
        )


class DirectionAndCellTests(unittest.TestCase):
    def test_increase_names_the_cell_entries(self):
        baseline = profile_of(shares(40, 200))
        population = mk_population(shares(40, 100))
        period = PopulationProfile.build(population)
        findings = compare_profiles(
            baseline, period, "by_preparer", "2025-06",
            entries=population.entries,
        )
        (f,) = findings
        self.assertEqual(len(f.entry_ids), 40)
        for eid in f.entry_ids:
            self.assertEqual(population.entry(eid).preparer_id, "P-01")
        self.assertEqual(list(f.entry_ids), sorted(f.entry_ids))

    def test_decrease_is_reported_but_names_no_entries(self):
        """A share that collapses is still drift. There are no entries to
        point at — the drift is in what is absent — so the finding carries
        none rather than being dropped."""
        # Two categories only, so the fall and its mirror are both visible.
        baseline = profile_of(["P-01"] * 120 + ["P-02"] * 80)   # P-01 at 0.60
        population = mk_population(["P-01"] * 30 + ["P-02"] * 70)  # 0.30
        period = PopulationProfile.build(population)
        findings = compare_profiles(
            baseline, period, "by_preparer", "2025-06",
            entries=population.entries,
        )
        by_cat = {f.category: f for f in findings}
        self.assertEqual(by_cat["P-01"].direction, "decrease")
        self.assertEqual(by_cat["P-01"].entry_ids, ())
        self.assertLess(by_cat["P-01"].shift, 0)
        # Its mirror image (P-02 rising) does name entries.
        self.assertEqual(by_cat["P-02"].direction, "increase")
        self.assertEqual(len(by_cat["P-02"].entry_ids), 70)

    def test_rare_baseline_categories_are_skipped(self):
        """A category with almost no baseline has no stable share to drift
        from; the screen says so in its limitations rather than reporting
        noise as a finding."""
        baseline = profile_of(["P-01"] * 195 + ["P-02"] * 5)
        period = profile_of(["P-01"] * 60 + ["P-02"] * 40)
        findings = compare_profiles(
            baseline, period, "by_preparer", "2025-06", DriftParams()
        )
        self.assertNotIn("P-02", [f.category for f in findings])
        # P-01's own fall is above the floor and is reported.
        self.assertEqual([f.category for f in findings], ["P-01"])

    def test_unsupported_dimension_fails_loudly(self):
        baseline = profile_of(shares(40, 200))
        with self.assertRaises(ValueError):
            compare_profiles(baseline, baseline, "by_account", "2025-06")
        with self.assertRaises(ValueError):
            DriftParams(dimensions=("by_account",))


class AnalyzeRefusalTests(unittest.TestCase):
    """Refusals are inconclusive outcomes with a reason, never a quiet
    "no drift" (DECISIONS D-011)."""

    def test_refuses_without_a_tested_period(self):
        led = generate(GeneratorConfig(seed=5, n_entries=200,
                                       start=date(2025, 1, 1),
                                       end=date(2025, 3, 31)))
        report = analyze(led, DriftParams(baseline_periods=3))
        self.assertFalse(report.applicable)
        self.assertIn("baseline", report.refusal_reason)
        self.assertEqual(report.findings, ())

    def test_refuses_a_baseline_too_thin_to_resolve_the_floor(self):
        led = generate(GeneratorConfig(seed=5, n_entries=120))
        report = analyze(led, DriftParams(min_baseline_entries=1000))
        self.assertFalse(report.applicable)
        self.assertIn("below the minimum", report.refusal_reason)

    def test_small_periods_are_untested_not_passed(self):
        led = generate(GeneratorConfig(seed=5, n_entries=400))
        report = analyze(led, DriftParams(min_period_entries=100))
        self.assertTrue(report.applicable)
        self.assertTrue(report.untested)
        for u in report.untested:
            self.assertNotIn(u.period, report.tested_periods)
            self.assertIn("below the minimum", u.reason)


class CleanPopulationBaseRateTests(unittest.TestCase):
    """The negative control: an undrifted population must not fire.

    Measured, not assumed (DECISIONS D-028). At ~200 entries per monthly
    batch the default parameters produce exactly zero findings across these
    seeds; the measurement behind the chosen floor, including the smaller
    batch sizes where the screen is *not* silent, is recorded in DECISIONS.
    """

    def test_clean_ledgers_produce_no_findings(self):
        for seed in (501, 502, 503):
            led = generate(GeneratorConfig(seed=seed, n_entries=2400))
            report = analyze(led)
            self.assertTrue(report.applicable, seed)
            self.assertEqual(len(report.tested_periods), 9, seed)
            self.assertEqual(
                [f.statement for f in report.findings], [], f"seed {seed}"
            )

    def test_the_control_can_fail(self):
        """Proof the negative control is capable of failing: the same clean
        ledgers fire immediately once the materiality floor is dropped to a
        level ordinary month-to-month variation clears."""
        fired = 0
        for seed in (501, 502, 503):
            led = generate(GeneratorConfig(seed=seed, n_entries=2400))
            fired += len(analyze(led, DriftParams(min_shift=0.01)).findings)
        self.assertGreater(fired, 0)


class ReportSerializationTests(unittest.TestCase):
    def test_report_is_deterministic_and_canonical(self):
        led = generate(GeneratorConfig(seed=7, n_entries=1200))
        a = analyze(led)
        b = analyze(led)
        self.assertEqual(canonical_bytes(a.to_dict()), canonical_bytes(b.to_dict()))
        d = a.to_dict()
        self.assertEqual(d["params"]["dimensions"], list(DEFAULT_DIMENSIONS))
        self.assertEqual(d["period_basis"], "posting_date")
        self.assertIsInstance(a, DriftReport)


if __name__ == "__main__":
    unittest.main()
