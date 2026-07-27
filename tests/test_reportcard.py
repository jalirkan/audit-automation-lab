import unittest
from datetime import date

from core.canonical import canonical_bytes
from core.stats import OUTCOME_EXCEPTION, OUTCOME_INCONCLUSIVE, proportion
from ledger.anomalies import Manifest, PlantedAnomaly, default_plan
from ledger.generate import GeneratorConfig
from reportcard.grade import Targets, build_report_card, grade_run
from rules.base import Flag, Rule
from rules.registry import build_rules
from tests.test_rules import mk_entry, mk_ledger


class FakeRule(Rule):
    """Deterministic stub: flags a fixed set of entry ids."""

    def __init__(self, rule_id, to_flag, targets=()):
        self.rule_id = rule_id
        self.targets = tuple(targets)
        self.to_flag = tuple(to_flag)
        self.title = f"fake {rule_id}"
        self.population_description = "all"
        self.criterion_description = "fixed"
        self.limitations = ("test stub",)

    def evaluate(self, ledger):
        return [
            Flag(self.rule_id, eid, "planted by test") for eid in self.to_flag
        ]


def _manifest(anomalies):
    return Manifest(generator_seed=0, anomaly_seed=0, plan={}, anomalies=tuple(anomalies))


class HandComputedTests(unittest.TestCase):
    """Small case computed by hand:

    5 entries E1..E5. Anomaly A = {E2} (class alpha), anomaly B = {E5}
    (class beta). Rule F1 (designed for alpha) flags E2, E3; rule F2
    (designed for nothing) flags E4.

    flagged = {E2, E3, E4}; planted = {E2, E5}; clean = {E1, E3, E4}.
    recall alpha: any 1/1, designed 1/1. recall beta: 0/1, missed.
    precision = 1/3. FP = flagged clean / clean = 2/3.
    """

    def setUp(self):
        entries = [
            mk_entry(f"JE-00000{i}", date(2025, 3, 9 + i)) for i in range(1, 6)
        ]
        self.led = mk_ledger(entries)
        self.man = _manifest(
            [
                PlantedAnomaly("AN-001", "alpha", ("JE-000002",), "a"),
                PlantedAnomaly("AN-002", "beta", ("JE-000005",), "b"),
            ]
        )
        self.rules = [
            FakeRule("F-001", ["JE-000002", "JE-000003"], targets=("alpha",)),
            FakeRule("F-002", ["JE-000004"]),
        ]

    def test_hand_computed_numbers(self):
        run = grade_run(self.led, self.man, rules=self.rules)
        self.assertEqual(run.n_flagged_entries, 3)
        self.assertEqual(run.n_planted_entries, 2)

        by_class = {c.anomaly_class: c for c in run.class_grades}
        alpha, beta = by_class["alpha"], by_class["beta"]
        self.assertEqual((alpha.n_detected_any, alpha.n_planted), (1, 1))
        self.assertEqual(alpha.n_detected_designed, 1)
        self.assertEqual(alpha.caught_by, {"AN-001": ["F-001"]})
        self.assertEqual((beta.n_detected_any, beta.n_planted), (0, 1))
        self.assertEqual(beta.missed, ("AN-002",))

        self.assertEqual(run.precision.numerator, 1)
        self.assertEqual(run.precision.n, 3)
        self.assertEqual(run.fp_rate.numerator, 2)
        self.assertEqual(run.fp_rate.n, 3)

        # Intervals are exactly the Wilson intervals from core.stats.
        self.assertEqual(
            run.precision.interval,
            proportion("x", 1, 3).interval,
        )

    def test_rule_grades(self):
        run = grade_run(self.led, self.man, rules=self.rules)
        by_rule = {r.rule_id: r for r in run.rule_grades}
        self.assertEqual(by_rule["F-001"].n_true, 1)
        self.assertEqual(by_rule["F-001"].n_false, 1)
        self.assertEqual(by_rule["F-002"].n_true, 0)
        self.assertEqual(by_rule["F-002"].n_false, 1)


CFG = GeneratorConfig(seed=0, n_entries=1000)
PLAN = default_plan()
SEEDS = (301, 302, 303)


class ReportCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.card = build_report_card(CFG, plan=PLAN, seeds=SEEDS)

    def test_full_battery_detects_every_class_at_these_seeds(self):
        for pooled in self.card.pooled_classes:
            self.assertEqual(
                pooled.n_detected, pooled.n_planted,
                f"{pooled.anomaly_class}: {pooled.per_seed}",
            )

    def test_small_pools_are_inconclusive_not_passes(self):
        """3 seeds x 2 instances = 6 per class: a 6/6 recall cannot clear a
        0.9 floor at 95% — the honest outcome is inconclusive."""
        for pooled in self.card.pooled_classes:
            self.assertEqual(pooled.n_planted, 6, pooled.anomaly_class)
            self.assertEqual(
                pooled.decision.outcome, OUTCOME_INCONCLUSIVE,
                pooled.anomaly_class,
            )
            self.assertLess(pooled.recall.interval[0], 0.9)

    def test_stability_reported_per_seed(self):
        for pooled in self.card.pooled_classes:
            self.assertEqual(set(pooled.per_seed), set(SEEDS))
            self.assertGreaterEqual(pooled.recall_max, pooled.recall_min)

    def test_precision_below_one_because_benign_structure_exists(self):
        """DECISIONS D-008 pays off here: the clean ledger's benign round
        rents, weekend batches and December cluster make precision a real
        number strictly below 1."""
        self.assertLess(self.card.pooled_precision.value, 1.0)
        self.assertGreater(self.card.pooled_precision.value, 0.0)
        self.assertGreater(self.card.pooled_fp_rate.value, 0.0)

    def test_deterministic(self):
        again = build_report_card(CFG, plan=PLAN, seeds=SEEDS)
        self.assertEqual(
            canonical_bytes(self.card.to_dict()), canonical_bytes(again.to_dict())
        )

    def test_serializes_canonically(self):
        d = self.card.to_dict()
        self.assertIn("definitions", d)
        self.assertIn("pooled_fp_per_10k", d)
        canonical_bytes(d)

    def test_seed_validation(self):
        with self.assertRaises(ValueError):
            build_report_card(CFG, seeds=())
        with self.assertRaises(ValueError):
            build_report_card(CFG, seeds=(1, 1))


class BrokenRuleRegressionTests(unittest.TestCase):
    """The report card is the regression detector: removing the only rule
    designed for a class drives that class's recall to zero and its
    decision to exception."""

    def test_dropping_self_approval_rule_is_caught(self):
        all_but_r009 = build_rules(
            ["R-001", "R-002", "R-003", "R-004", "R-005", "R-006",
             "R-007", "R-008", "R-010", "R-011"]
        )
        card = build_report_card(
            CFG, plan=PLAN, seeds=(301, 302), rules=all_but_r009
        )
        by_class = {c.anomaly_class: c for c in card.pooled_classes}
        broken = by_class["self_approval"]
        self.assertEqual(broken.n_detected, 0)
        self.assertEqual(broken.decision.outcome, OUTCOME_EXCEPTION)
        # Classes with intact designed rules are unaffected.
        self.assertEqual(
            by_class["unbalanced_entry"].n_detected,
            by_class["unbalanced_entry"].n_planted,
        )


if __name__ == "__main__":
    unittest.main()
