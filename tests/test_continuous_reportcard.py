import unittest

from continuous.drift import DriftParams
from core.canonical import canonical_bytes
from core.stats import OUTCOME_EXCEPTION, OUTCOME_INCONCLUSIVE
from ledger.drift import DRIFT_CLASSES, default_drift_plan, generate_with_drift
from ledger.generate import GeneratorConfig
from report.renderers import render_html, render_markdown
from report.workpapers import build_report_card_document
from reportcard.grade import build_report_card
from rules.drift import ProfileDriftRule
from rules.registry import continuous_rules, default_rules

CFG = GeneratorConfig(seed=0, n_entries=2400)
PLAN = default_drift_plan()
SEEDS = (501, 502, 503)


def _card(seeds=SEEDS, rules=None, plan=PLAN):
    return build_report_card(
        CFG,
        plan=plan,
        seeds=seeds,
        rules=continuous_rules() if rules is None else rules,
        generate=generate_with_drift,
    )


class ContinuousReportCardTests(unittest.TestCase):
    """Drift is graded by the same card, against the same definitions, as
    every other planted class. A new detection capability that came with its
    own scorer would be a claim scored by its own author."""

    @classmethod
    def setUpClass(cls):
        cls.card = _card()

    def test_every_drift_class_is_detected_at_these_seeds(self):
        self.assertEqual(
            sorted(c.anomaly_class for c in self.card.pooled_classes),
            sorted(DRIFT_CLASSES),
        )
        for pooled in self.card.pooled_classes:
            self.assertEqual(
                pooled.n_detected, pooled.n_planted,
                f"{pooled.anomaly_class}: {pooled.per_seed}",
            )

    def test_small_pools_are_inconclusive_not_passes(self):
        """3 seeds x 2 instances = 6 per class: 6/6 cannot clear a 0.9 floor
        at 95%, and the card says inconclusive (DECISIONS D-020) rather than
        parading a hollow 100% for a brand-new detector."""
        for pooled in self.card.pooled_classes:
            self.assertEqual(pooled.n_planted, 6, pooled.anomaly_class)
            self.assertEqual(pooled.decision.outcome, OUTCOME_INCONCLUSIVE)
            self.assertLess(pooled.recall.interval[0], 0.9)

    def test_the_design_link_reaches_the_card(self):
        for pooled in self.card.pooled_classes:
            self.assertEqual(pooled.designed_rules, ("R-012",))

    def test_precision_is_capped_by_cell_composition_and_says_so(self):
        """The screen names a whole drifted cell as leads, so its
        entry-level precision cannot reach 1.0: the cell's legitimate
        members are counted as the false positives they are (D-029). The
        card prints the real number instead of grading the screen on a
        definition invented to flatter it."""
        precision = self.card.pooled_precision
        self.assertGreater(precision.value, 0.5)
        self.assertLess(precision.value, 1.0)
        self.assertGreater(self.card.pooled_fp_rate.value, 0.0)
        # Those false positives are entries the screen deliberately named,
        # not stray hits: every run's clean hits are non-zero and bounded by
        # the flagged total.
        for run in self.card.runs:
            self.assertGreater(run.n_flagged_entries, run.n_planted_entries)

    def test_stability_reported_per_seed(self):
        for pooled in self.card.pooled_classes:
            self.assertEqual(set(pooled.per_seed), set(SEEDS))
            self.assertGreaterEqual(pooled.recall_max, pooled.recall_min)

    def test_deterministic(self):
        again = _card()
        self.assertEqual(
            canonical_bytes(self.card.to_dict()), canonical_bytes(again.to_dict())
        )

    def test_renders_through_the_guarded_renderers(self):
        doc = build_report_card_document(self.card)
        md = render_markdown(doc)
        html = render_html(doc)
        self.assertIn("preparer_concentration_drift", md)
        self.assertIn("wilson", md)
        for banned in ("http://", "https://", "<script", "<link"):
            self.assertNotIn(banned, html)

    def test_alternate_generator_requires_its_own_plan(self):
        """The point-in-time default plan names classes the drift generator
        cannot plant; silently passing it through would raise deep inside
        generation with an unhelpful message."""
        with self.assertRaises(ValueError) as ctx:
            build_report_card(CFG, seeds=SEEDS, generate=generate_with_drift)
        self.assertIn("plan is required", str(ctx.exception))


class DisabledDriftDetectorTests(unittest.TestCase):
    """The report card is the regression detector (DECISIONS D-021), and it
    has to be able to fail. Two ways of breaking the screen, both caught:
    removing it, and leaving it in place with a floor it can never clear."""

    def test_removing_the_only_designed_rule_drives_recall_to_zero(self):
        card = _card(seeds=(501, 502), rules=[])
        for pooled in card.pooled_classes:
            self.assertEqual(pooled.n_detected, 0, pooled.anomaly_class)
            self.assertEqual(pooled.decision.outcome, OUTCOME_EXCEPTION)
            # designed_rules reflects the battery actually graded.
            self.assertEqual(pooled.designed_rules, ())

    def test_a_detuned_detector_fails_its_ground_truth_check(self):
        """The subtler regression: R-012 is present, targets the classes,
        and runs — but a materiality floor of 0.95 means it can never fire.
        Recall collapses while the design link stays intact, which is
        exactly the case a "rule is registered" check would wave through."""
        detuned = [ProfileDriftRule(DriftParams(min_shift=0.95))]
        card = _card(seeds=(501, 502), rules=detuned)
        for pooled in card.pooled_classes:
            self.assertEqual(pooled.n_detected, 0, pooled.anomaly_class)
            self.assertEqual(pooled.decision.outcome, OUTCOME_EXCEPTION)
            self.assertEqual(pooled.designed_rules, ("R-012",))
        # Nothing was flagged at all, so precision is "not tested", not 0.
        self.assertEqual(card.pooled_precision.n, 0)

    def test_the_point_in_time_battery_cannot_stand_in_for_the_drift_screen(self):
        """Why the batteries are graded apart (DECISIONS D-030): the eleven
        point-in-time rules do hit a few planted drift entries incidentally —
        a December plant meets the period-end screen — so a mixed battery
        would credit drift recall to rules that detected no drift at all.
        Graded honestly on its own, the point-in-time battery takes an
        exception on every drift class."""
        card = _card(rules=default_rules())
        for pooled in card.pooled_classes:
            self.assertEqual(pooled.designed_rules, ())
            self.assertLess(pooled.n_detected, pooled.n_planted)
            self.assertEqual(pooled.decision.outcome, OUTCOME_EXCEPTION)


if __name__ == "__main__":
    unittest.main()
