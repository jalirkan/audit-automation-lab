"""Grading the AP battery against planted duplicate invoices.

Same card, same definitions, same Wilson intervals, same interval-vs-target
decisions as every other planted class (DECISIONS D-029): a new detection
capability that arrived with its own scorer would be a claim graded by its
author. What is new here is the class split — four duplicate mechanisms
rather than one — and the split has to earn its keep: each class is the one
that collapses when a specific, plausible mis-tuning is made, and a card
that pooled them into a single "duplicate invoice" number would average
those failures out of sight (D-034).
"""

import unittest

from core.canonical import canonical_bytes
from core.stats import OUTCOME_EXCEPTION, OUTCOME_INCONCLUSIVE
from ledger.ap import (
    AP_DUPLICATE_CLASSES,
    default_ap_plan,
    generate_ap_with_duplicates,
)
from ledger.generate import GeneratorConfig
from report.renderers import render_html, render_markdown
from report.workpapers import build_report_card_document
from reportcard.grade import build_report_card
from rules.ap import DuplicateInvoiceAmountDateRule, DuplicateInvoiceReferenceRule
from rules.registry import ap_rules, default_rules

CFG = GeneratorConfig(seed=0, n_entries=900)
PLAN = default_ap_plan(2)      # four instances of each class per seed
SEEDS = (601, 602, 603)


def _card(seeds=SEEDS, rules=None, plan=PLAN):
    return build_report_card(
        CFG,
        plan=plan,
        seeds=seeds,
        rules=ap_rules() if rules is None else rules,
        generate=generate_ap_with_duplicates,
    )


def _pooled_rule_counts(card) -> dict:
    """rule_id -> (flags, planted hits, clean hits) across every run."""
    out = {}
    for run in card.runs:
        for rg in run.rule_grades:
            agg = out.setdefault(rg.rule_id, [0, 0, 0])
            agg[0] += rg.n_flags
            agg[1] += rg.n_true
            agg[2] += rg.n_false
    return {k: tuple(v) for k, v in out.items()}


class APReportCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.card = _card()

    def test_every_duplicate_class_is_graded(self):
        self.assertEqual(
            sorted(c.anomaly_class for c in self.card.pooled_classes),
            sorted(AP_DUPLICATE_CLASSES),
        )

    def test_every_class_is_detected_at_these_seeds(self):
        for pooled in self.card.pooled_classes:
            self.assertEqual(
                pooled.n_detected, pooled.n_planted,
                f"{pooled.anomaly_class}: {pooled.per_seed}",
            )

    def test_small_pools_are_inconclusive_not_passes(self):
        """3 seeds x 4 instances = 12 per class: 12/12 cannot clear a 0.9
        floor at 95%, and the card says inconclusive (D-020) rather than
        parading a hollow 100% for a brand-new screen. The measurement that
        does clear the floor is a wider run, recorded in DECISIONS D-035."""
        for pooled in self.card.pooled_classes:
            self.assertEqual(pooled.n_planted, 12, pooled.anomaly_class)
            self.assertEqual(pooled.decision.outcome, OUTCOME_INCONCLUSIVE)
            self.assertLess(pooled.recall.interval[0], 0.9)

    def test_the_design_link_reaches_the_card(self):
        designed = {
            c.anomaly_class: c.designed_rules for c in self.card.pooled_classes
        }
        self.assertEqual(designed["ap_exact_rekey"], ("AP-001",))
        self.assertEqual(designed["ap_cross_period_rekey"], ("AP-001",))
        self.assertEqual(designed["ap_transposed_reference"], ("AP-001",))
        self.assertEqual(designed["ap_no_reference_match"], ("AP-002",))

    def test_the_two_screens_have_very_different_precision(self):
        """The point of running both: a document-key match is nearly clean,
        and an amount-and-date match is not. Averaging them into one
        'duplicate detection' number would hide which evidence bought which
        recall (DECISIONS D-035)."""
        counts = _pooled_rule_counts(self.card)
        key_flags, key_true, key_false = counts["AP-001"]
        amt_flags, amt_true, amt_false = counts["AP-002"]
        self.assertGreater(key_true / key_flags, 0.7)
        self.assertLess(amt_true / amt_flags, 0.5)
        # Neither screen is free, and neither is silent.
        self.assertGreater(key_false, 0)
        self.assertGreater(amt_false, amt_true)

    def test_false_positives_are_real_and_reported_with_their_n(self):
        self.assertGreater(self.card.pooled_fp_rate.value, 0.0)
        self.assertGreater(self.card.pooled_fp_rate.n, 0)
        self.assertIn("n=", self.card.pooled_fp_rate.render())

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
        self.assertIn("ap_exact_rekey", md)
        self.assertIn("wilson", md)
        for banned in ("http://", "https://", "<script", "<link"):
            self.assertNotIn(banned, html)

    def test_alternate_generator_requires_its_own_plan(self):
        with self.assertRaises(ValueError) as ctx:
            build_report_card(CFG, seeds=SEEDS, generate=generate_ap_with_duplicates)
        self.assertIn("plan is required", str(ctx.exception))


class BrokenDetectorTests(unittest.TestCase):
    """The report card is the regression detector (DECISIONS D-021), and it
    has to be able to fail. Both directions are exercised: a screen removed
    entirely, and screens left registered, targeting their classes, running
    on every entry — and mis-tuned in ways an auditor might plausibly choose.
    Each mutation kills exactly the class the split exists to isolate."""

    def test_removing_the_battery_drives_every_class_to_zero(self):
        card = _card(seeds=(601, 602), rules=[])
        for pooled in card.pooled_classes:
            self.assertEqual(pooled.n_detected, 0, pooled.anomaly_class)
            self.assertEqual(pooled.decision.outcome, OUTCOME_EXCEPTION)
            self.assertEqual(pooled.designed_rules, ())
        self.assertEqual(card.pooled_precision.n, 0)

    def test_a_seven_day_window_loses_the_cross_period_class(self):
        """The mis-tuning this class exists for: the GL duplicate rule
        bounds its window at seven days, and porting that bound to a
        document key is an easy, wrong call. AP-001 is still registered,
        still targets the class, still flags the near re-keys — and
        cross-period recall goes to zero."""
        detuned = [
            DuplicateInvoiceReferenceRule(window_days=7),
            DuplicateInvoiceAmountDateRule(),
        ]
        card = _card(seeds=(601, 602), rules=detuned)
        by_class = {c.anomaly_class: c for c in card.pooled_classes}
        cross = by_class["ap_cross_period_rekey"]
        self.assertEqual(cross.n_detected, 0)
        self.assertEqual(cross.decision.outcome, OUTCOME_EXCEPTION)
        self.assertEqual(cross.designed_rules, ("AP-001",))
        # The classes the window does not touch are still caught, so the
        # failure is attributable rather than a general collapse.
        for name in ("ap_transposed_reference", "ap_no_reference_match"):
            self.assertEqual(
                by_class[name].n_detected, by_class[name].n_planted, name
            )
        # Even the easy class loses instances: a re-key two to five business
        # days later can be more than seven calendar days later.
        near = by_class["ap_exact_rekey"]
        self.assertLess(near.n_detected, near.n_planted)

    def test_dropping_transposition_matching_loses_that_class(self):
        """Detuned in the *full* battery, so the other screen is there to
        catch what falls: it does not. The two rules partition the same
        space on one shared definition of a reference match, so AP-002 still
        recognises the transposition, still defers the pair to AP-001, and
        AP-001 no longer matches it. The pair falls through the crack — a
        battery whose screens disagree about the boundary leaves a gap, and
        the class is what makes the gap visible."""
        detuned = [
            DuplicateInvoiceReferenceRule(allow_transposed=False),
            DuplicateInvoiceAmountDateRule(),
        ]
        card = _card(seeds=(601, 602), rules=detuned)
        by_class = {c.anomaly_class: c for c in card.pooled_classes}
        transposed = by_class["ap_transposed_reference"]
        self.assertEqual(transposed.n_detected, 0)
        self.assertEqual(transposed.decision.outcome, OUTCOME_EXCEPTION)
        self.assertEqual(transposed.designed_rules, ("AP-001",))
        for name in ("ap_exact_rekey", "ap_cross_period_rekey",
                     "ap_no_reference_match"):
            self.assertEqual(
                by_class[name].n_detected, by_class[name].n_planted, name
            )

    def test_the_two_screens_claim_each_pair_exactly_once(self):
        """The partition, asserted rather than assumed: every planted pair
        is claimed by exactly one of the two screens. A pair claimed by
        neither is a duplicate nobody looks for, and a pair claimed by both
        would double-count the same evidence in the precision denominator."""
        card = _card(seeds=(601,))
        run = card.runs[0]
        for cg in run.class_grades:
            for rules_hit in cg.caught_by.values():
                self.assertEqual(len(rules_hit), 1, cg.anomaly_class)
            self.assertEqual(cg.missed, ())

    def test_an_exact_invoice_date_window_loses_most_of_the_last_class(self):
        """AP-002 with a zero-day window still runs, still targets the
        class, and still flags every same-day pair — but a statement copy
        re-keyed under a shifted invoice date walks past it."""
        detuned = [
            DuplicateInvoiceReferenceRule(),
            DuplicateInvoiceAmountDateRule(window_days=0),
        ]
        card = _card(seeds=(601, 602), rules=detuned)
        by_class = {c.anomaly_class: c for c in card.pooled_classes}
        loose = by_class["ap_no_reference_match"]
        self.assertLess(loose.n_detected, loose.n_planted // 2)
        self.assertEqual(loose.decision.outcome, OUTCOME_EXCEPTION)
        self.assertEqual(loose.designed_rules, ("AP-002",))

    def test_the_general_ledger_battery_cannot_stand_in(self):
        """Why the batteries are graded apart (D-030, applied again in
        D-033): the eleven point-in-time rules do catch a few planted
        duplicates incidentally — R-010 fires when the re-key happens to
        share the original's preparer and line structure — so a mixed
        battery would credit AP recall to screens that read no document
        field at all. Graded honestly on its own, the GL battery takes an
        exception on every AP class."""
        card = _card(rules=default_rules())
        for pooled in card.pooled_classes:
            self.assertEqual(pooled.designed_rules, ())
            self.assertLess(pooled.n_detected, pooled.n_planted)
            self.assertEqual(pooled.decision.outcome, OUTCOME_EXCEPTION)
        by_class = {c.anomaly_class: c for c in card.pooled_classes}
        # The two mechanisms a preparer-and-line-structure screen cannot see
        # at all, whatever its window.
        self.assertEqual(by_class["ap_transposed_reference"].n_detected, 0)
        self.assertEqual(by_class["ap_cross_period_rekey"].n_detected, 0)


if __name__ == "__main__":
    unittest.main()
