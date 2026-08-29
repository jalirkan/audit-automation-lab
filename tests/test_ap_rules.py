"""The accounts-payable battery, rule by rule.

Every rule gets a fixture that triggers it and one that does not — the
PLAN Phase 1 discipline — and the two screens' boundary with each other is
tested from both sides, because a pair that neither rule claims is a
duplicate nobody looks for.
"""

import unittest
from datetime import date

from ledger.ap import generate_ap_subledger
from ledger.generate import GeneratorConfig, default_chart, default_users, generate
from ledger.model import JournalEntry, JournalLine, Ledger, SourceDocument
from report.language import find_bare_rates, find_prohibited
from report.renderers import render_html, render_markdown
from report.workpapers import build_rule_workpaper
from rules.ap import (
    DEFAULT_INVOICE_DATE_WINDOW,
    DuplicateInvoiceAmountDateRule,
    DuplicateInvoiceReferenceRule,
    is_transposition,
    reference_match,
)
from rules.registry import ap_rules, evaluate_all

USERS = default_users(3, 2)


def invoice(
    n,
    vendor="V-01",
    reference="INV-10001",
    cents=123_456,
    doc_date=date(2025, 3, 10),
    posting_date=None,
    preparer="P-01",
    account="6400",
    doc_type="invoice",
):
    posting_date = posting_date or doc_date
    if doc_type == "invoice":
        lines = (
            JournalLine(account, debit_cents=cents),
            JournalLine("2000", credit_cents=cents),
        )
    else:
        lines = (
            JournalLine("2000", debit_cents=cents),
            JournalLine(account, credit_cents=cents),
        )
    return JournalEntry(
        entry_id=f"JE-{n:06d}",
        posting_date=posting_date,
        effective_date=doc_date,
        description=f"vendor {vendor} document {reference}",
        source="AP",
        preparer_id=preparer,
        approver_id=None,
        lines=lines,
        document=SourceDocument(
            doc_type=doc_type,
            party_id=vendor,
            reference=reference,
            doc_date=doc_date,
        ),
    )


def ledger(*entries) -> Ledger:
    return Ledger(
        coa=default_chart(),
        users=USERS,
        entries=tuple(entries),
        meta={
            "seed": 0,
            "fiscal_year_start": "2025-01-01",
            "fiscal_year_end": "2025-12-31",
            "approval_threshold_cents": 1_000_000,
            "subledger": "accounts_payable",
        },
    )


def flagged(rule, led) -> set:
    return {f.entry_id for f in rule.evaluate(led)}


class TranspositionTests(unittest.TestCase):
    def test_adjacent_swap_matches(self):
        self.assertTrue(is_transposition("INV-1234", "INV-2134"))

    def test_distant_swap_matches_too(self):
        """The criterion is not narrowed to adjacency. The planted keying
        error is the adjacent swap, and a criterion cut to the plant's own
        shape would grade itself."""
        self.assertTrue(is_transposition("1234", "4231"))

    def test_single_mis_keyed_digit_is_not_a_transposition(self):
        self.assertFalse(is_transposition("INV-1234", "INV-1235"))

    def test_two_unrelated_digits_are_not_a_transposition(self):
        self.assertFalse(is_transposition("1234", "5634"))

    def test_letters_are_not_swapped(self):
        self.assertFalse(is_transposition("AB12", "BA12"))

    def test_length_and_identity(self):
        self.assertFalse(is_transposition("1234", "12345"))
        self.assertFalse(is_transposition("1234", "1234"))

    def test_reference_match_names_its_basis(self):
        self.assertEqual(reference_match("A1", "A1"), "exact")
        self.assertEqual(reference_match("A12", "A21"), "transposed")
        self.assertEqual(reference_match("A12", "A21", allow_transposed=False), "")
        self.assertEqual(reference_match("A12", "B99"), "")


class DocumentKeyRuleTests(unittest.TestCase):
    def test_same_reference_and_amount_flags_both_documents(self):
        led = ledger(
            invoice(1, posting_date=date(2025, 3, 10)),
            invoice(2, posting_date=date(2025, 3, 14)),
        )
        self.assertEqual(
            flagged(DuplicateInvoiceReferenceRule(), led), {"JE-000001", "JE-000002"}
        )

    def test_distance_is_not_part_of_the_criterion(self):
        """A vendor does not issue one reference twice, so a re-key found
        eight months later is the same finding as one found the next day."""
        led = ledger(
            invoice(1, posting_date=date(2025, 1, 6)),
            invoice(2, posting_date=date(2025, 9, 8)),
        )
        self.assertEqual(len(flagged(DuplicateInvoiceReferenceRule(), led)), 2)

    def test_a_bounded_window_misses_the_distant_pair(self):
        """The naive port of the GL duplicate rule, which bounds its window
        because identical *line structure* legitimately repeats. That
        reasoning does not carry over to a document key, and the
        cross-period class exists to make the difference measurable."""
        led = ledger(
            invoice(1, posting_date=date(2025, 1, 6)),
            invoice(2, posting_date=date(2025, 9, 8)),
        )
        self.assertEqual(flagged(DuplicateInvoiceReferenceRule(window_days=7), led), set())

    def test_same_reference_with_different_amounts_is_not_flagged(self):
        """Progress billing against one invoice number: the instalments are
        unequal, and the rule requires equal amounts."""
        led = ledger(
            invoice(1, cents=600_000, posting_date=date(2025, 3, 10)),
            invoice(2, cents=400_000, posting_date=date(2025, 4, 10)),
        )
        self.assertEqual(flagged(DuplicateInvoiceReferenceRule(), led), set())

    def test_same_reference_from_different_vendors_is_not_flagged(self):
        led = ledger(
            invoice(1, vendor="V-01"),
            invoice(2, vendor="V-02", posting_date=date(2025, 3, 12)),
        )
        self.assertEqual(flagged(DuplicateInvoiceReferenceRule(), led), set())

    def test_transposed_reference_is_flagged(self):
        led = ledger(
            invoice(1, reference="INV-10001"),
            invoice(2, reference="INV-01001", posting_date=date(2025, 3, 13)),
        )
        flags = DuplicateInvoiceReferenceRule().evaluate(led)
        self.assertEqual(len(flags), 2)
        self.assertEqual(flags[0].details["basis"], "transposed")

    def test_transposition_matching_can_be_switched_off(self):
        led = ledger(
            invoice(1, reference="INV-10001"),
            invoice(2, reference="INV-01001", posting_date=date(2025, 3, 13)),
        )
        self.assertEqual(
            flagged(DuplicateInvoiceReferenceRule(allow_transposed=False), led), set()
        )

    def test_one_mis_keyed_digit_is_deliberately_not_matched(self):
        """Vendors number sequentially: a reference one digit away is
        ordinarily the next invoice, and matching it would buy recall at a
        false-positive cost this population cannot bound."""
        led = ledger(
            invoice(1, reference="INV-10001"),
            invoice(2, reference="INV-10002", posting_date=date(2025, 3, 13)),
        )
        self.assertEqual(flagged(DuplicateInvoiceReferenceRule(), led), set())

    def test_credit_memos_are_outside_the_population(self):
        led = ledger(
            invoice(1, reference="INV-10001"),
            invoice(2, reference="INV-10001", doc_type="credit_memo",
                    posting_date=date(2025, 3, 15)),
        )
        self.assertEqual(flagged(DuplicateInvoiceReferenceRule(), led), set())
        self.assertEqual(DuplicateInvoiceReferenceRule().population_size(led), 1)


class AmountDateRuleTests(unittest.TestCase):
    def test_unrelated_references_within_the_window_are_flagged(self):
        led = ledger(
            invoice(1, reference="INV-10001", doc_date=date(2025, 3, 10)),
            invoice(2, reference="INV-40777", doc_date=date(2025, 3, 12)),
        )
        self.assertEqual(
            flagged(DuplicateInvoiceAmountDateRule(), led), {"JE-000001", "JE-000002"}
        )

    def test_a_key_match_belongs_to_the_other_rule(self):
        for other in ("INV-10001", "INV-01001"):
            led = ledger(
                invoice(1, reference="INV-10001", doc_date=date(2025, 3, 10)),
                invoice(2, reference=other, doc_date=date(2025, 3, 12)),
            )
            self.assertEqual(flagged(DuplicateInvoiceAmountDateRule(), led), set(), other)

    def test_invoice_dates_outside_the_window_are_not_flagged(self):
        led = ledger(
            invoice(1, reference="INV-10001", doc_date=date(2025, 3, 3)),
            invoice(2, reference="INV-40777", doc_date=date(2025, 4, 3)),
        )
        self.assertEqual(flagged(DuplicateInvoiceAmountDateRule(), led), set())

    def test_the_window_is_on_invoice_dates_not_posting_dates(self):
        """The same document keyed twice carries one document date however
        long the second keying took."""
        led = ledger(
            invoice(1, reference="INV-10001", doc_date=date(2025, 3, 3),
                    posting_date=date(2025, 3, 4)),
            invoice(2, reference="INV-40777", doc_date=date(2025, 3, 5),
                    posting_date=date(2025, 6, 20)),
        )
        self.assertEqual(len(flagged(DuplicateInvoiceAmountDateRule(), led)), 2)

    def test_different_amounts_are_not_flagged(self):
        led = ledger(
            invoice(1, reference="INV-10001", cents=100_000),
            invoice(2, reference="INV-40777", cents=100_001),
        )
        self.assertEqual(flagged(DuplicateInvoiceAmountDateRule(), led), set())

    def test_credit_memos_are_excluded_and_the_exclusion_is_load_bearing(self):
        """A reversal carries the vendor, amount and dates of the invoice it
        cancels. The companion half of this test proves the exclusion does
        something: switch the scoping parameter and the reversal is flagged
        (toolkit D-030 discipline — a guard is only a guard if it fires)."""
        led = ledger(
            invoice(1, reference="INV-10001", doc_date=date(2025, 3, 10)),
            invoice(2, reference="CM-55", doc_date=date(2025, 3, 14),
                    doc_type="credit_memo"),
        )
        self.assertEqual(flagged(DuplicateInvoiceAmountDateRule(), led), set())
        self.assertEqual(
            flagged(DuplicateInvoiceAmountDateRule(include_credit_memos=True), led),
            {"JE-000001", "JE-000002"},
        )

    def test_negative_window_is_refused(self):
        with self.assertRaises(ValueError):
            DuplicateInvoiceAmountDateRule(window_days=-1)


class ApplicabilityTests(unittest.TestCase):
    def test_the_battery_refuses_a_general_ledger(self):
        """A rule that cannot read its population refuses and says why
        (DECISIONS D-011); it does not silently examine nothing and pass."""
        gl = generate(GeneratorConfig(seed=5, n_entries=300))
        for rule in ap_rules():
            ok, reason = rule.applicable(gl)
            self.assertFalse(ok, rule.rule_id)
            self.assertIn("general ledger", reason)

    def test_a_subledger_of_credit_memos_only_is_refused(self):
        led = ledger(invoice(1, doc_type="credit_memo"))
        for rule in ap_rules():
            ok, reason = rule.applicable(led)
            self.assertFalse(ok, rule.rule_id)
            self.assertIn("no vendor invoice documents", reason)

    def test_refusal_reaches_the_battery_result(self):
        gl = generate(GeneratorConfig(seed=5, n_entries=300))
        results = evaluate_all(gl, rules=ap_rules())
        for rid, res in results.items():
            self.assertFalse(res["applicable"], rid)
            self.assertEqual(res["flags"], [])
            self.assertEqual(res["population_size"], 0)


class BatteryOnGeneratedSubledgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.led = generate_ap_subledger(GeneratorConfig(seed=602, n_entries=900))
        cls.results = evaluate_all(cls.led, rules=ap_rules())

    def test_both_rules_run(self):
        self.assertEqual(sorted(self.results), ["AP-001", "AP-002"])
        for rid, res in self.results.items():
            self.assertTrue(res["applicable"], f"{rid}: {res['reason']}")
            self.assertGreater(res["population_size"], 0)

    def test_flags_are_deterministic(self):
        again = evaluate_all(self.led, rules=ap_rules())
        for rid in self.results:
            self.assertEqual(
                [f.to_dict() for f in self.results[rid]["flags"]],
                [f.to_dict() for f in again[rid]["flags"]],
                rid,
            )

    def test_the_clean_population_is_not_silent_and_says_why(self):
        """AP-002's yield on a clean subledger is the split billing it
        cannot distinguish from a re-key. That cost is measured, not
        engineered away (DECISIONS D-035)."""
        self.assertGreater(len(self.results["AP-002"]["flags"]), 0)
        self.assertLess(
            len(self.results["AP-002"]["flags"]), 0.1 * len(self.led)
        )

    def test_workpapers_render_through_both_guards(self):
        for rid, res in self.results.items():
            doc = build_rule_workpaper(res, self.led)
            md = render_markdown(doc)
            html = render_html(doc)
            self.assertEqual(find_prohibited(md), [], rid)
            self.assertEqual(find_bare_rates(md), [], rid)
            for banned in ("http://", "https://", "<script", "<link"):
                self.assertNotIn(banned, html)
            self.assertIn(rid, md)

    def test_the_default_window_sits_below_the_monthly_recurrence(self):
        """The materiality choice D-035 records: an invoice-date window at
        or above the monthly cadence sweeps every recurring charge in."""
        self.assertLess(DEFAULT_INVOICE_DATE_WINDOW, 28)
        wide = DuplicateInvoiceAmountDateRule(window_days=31).evaluate(self.led)
        narrow = DuplicateInvoiceAmountDateRule().evaluate(self.led)
        self.assertGreater(len(wide), len(narrow))


if __name__ == "__main__":
    unittest.main()
