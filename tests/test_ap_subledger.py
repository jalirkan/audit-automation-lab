"""The AP subledger and its planted duplicates.

Two jobs here, the same two the GL injector's tests do: prove the population
is what it claims to be (so its base rates mean something), and prove every
plant actually has the property its manifest note asserts — a manifest is
ground truth only if the plants are real.
"""

import collections
import unittest
from datetime import timedelta

from core.canonical import canonical_bytes
from core.dates import holidays_for_range, is_business_day, period_str
from ledger.ap import (
    AP_CONTROL_ACCOUNT,
    AP_DUPLICATE_CLASSES,
    PROGRESS_VENDOR,
    PROMPT_KEYING_LAG,
    RECURRING_CENTS,
    RECURRING_VENDOR,
    SPLIT_VENDOR,
    default_ap_plan,
    generate_ap_subledger,
    generate_ap_with_duplicates,
    transposition_candidates,
)
from ledger.anomalies import Manifest
from ledger.generate import GeneratorConfig
from rules.ap import is_transposition

CFG = GeneratorConfig(seed=601, n_entries=900)
HOLIDAYS = holidays_for_range(CFG.start, CFG.end)


def keying_lag(entry) -> int:
    """Business days between the document's date and the day it was keyed."""
    n = 0
    d = entry.document.doc_date
    while d < entry.posting_date:
        d += timedelta(days=1)
        if is_business_day(d, HOLIDAYS):
            n += 1
    return n


class SubledgerShapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.led = generate_ap_subledger(CFG)

    def test_every_entry_carries_a_source_document(self):
        for e in self.led.entries:
            self.assertIsNotNone(e.document, e.entry_id)
            self.assertEqual(e.document.party_id[:2], "V-")
            self.assertTrue(e.document.reference)

    def test_entry_count_and_ordering(self):
        self.assertEqual(len(self.led), CFG.n_entries)
        dates = [e.posting_date for e in self.led.entries]
        self.assertEqual(dates, sorted(dates))
        for i, e in enumerate(self.led.entries, start=1):
            self.assertEqual(e.entry_id, f"JE-{i:06d}")

    def test_invoices_credit_the_payables_control_account(self):
        for e in self.led.entries:
            if e.document.doc_type != "invoice":
                continue
            self.assertEqual(e.credit_account_ids, (AP_CONTROL_ACCOUNT,))
            self.assertTrue(e.is_balanced)

    def test_credit_memos_run_the_other_way(self):
        memos = [e for e in self.led.entries if e.document.doc_type == "credit_memo"]
        self.assertTrue(memos)
        for e in memos:
            self.assertEqual(e.debit_account_ids, (AP_CONTROL_ACCOUNT,))

    def test_effective_date_is_the_document_date(self):
        for e in self.led.entries:
            self.assertEqual(e.effective_date, e.document.doc_date)

    def test_deterministic(self):
        again = generate_ap_subledger(CFG)
        self.assertEqual(
            canonical_bytes(self.led.to_dict()), canonical_bytes(again.to_dict())
        )

    def test_csv_carries_the_document_columns(self):
        header, first = self.led.entries_csv().splitlines()[:2]
        self.assertTrue(header.endswith("doc_type,doc_party,doc_reference,doc_date"))
        self.assertIn("invoice", first)


class BenignStructureTests(unittest.TestCase):
    """The clean subledger contains look-alikes on purpose (D-008 applied to
    AP): without them the duplicate screens would measure precision 1.0 by
    construction. The counts are pinned exactly, so a change to the
    population that quietly removes a look-alike fails here rather than
    flattering a report card later."""

    @classmethod
    def setUpClass(cls):
        cls.led = generate_ap_subledger(CFG)

    def test_monthly_retainer_repeats_one_amount_twelve_times(self):
        hits = [
            e
            for e in self.led.entries
            if e.document.party_id == RECURRING_VENDOR
            and e.amount_cents == RECURRING_CENTS
        ]
        self.assertEqual(len(hits), 12)
        self.assertEqual(len({e.document.reference for e in hits}), 12)
        gaps = sorted(
            (b.document.doc_date - a.document.doc_date).days
            for a, b in zip(
                sorted(hits, key=lambda e: e.document.doc_date),
                sorted(hits, key=lambda e: e.document.doc_date)[1:],
            )
        )
        # Every gap is a month: this is what sets the ceiling on AP-002's
        # window, and DECISIONS D-035 records the measurement.
        self.assertGreaterEqual(min(gaps), 28)

    def test_same_day_split_billing_pairs(self):
        split = [e for e in self.led.entries if e.document.party_id == SPLIT_VENDOR]
        groups = collections.Counter(
            (e.document.doc_date, e.amount_cents) for e in split
        )
        pairs = [k for k, v in groups.items() if v >= 2]
        self.assertEqual(len(pairs), 12)

    def test_progress_billings_repeat_a_reference_with_unequal_amounts(self):
        groups = collections.defaultdict(list)
        for e in self.led.entries:
            if e.document.party_id == PROGRESS_VENDOR:
                groups[e.document.reference].append(e)
        pairs = [v for v in groups.values() if len(v) == 2]
        self.assertEqual(len(pairs), 4)
        even = [p for p in pairs if p[0].amount_cents == p[1].amount_cents]
        # Exactly one instalment plan splits evenly, and it is the residual
        # false positive AP-001 owns rather than tunes away.
        self.assertEqual(len(even), 1)

    def test_credit_memos_reverse_an_invoice_of_the_same_amount(self):
        memos = [e for e in self.led.entries if e.document.doc_type == "credit_memo"]
        self.assertEqual(len(memos), 6)
        for memo in memos:
            twin = [
                e
                for e in self.led.entries
                if e.document.doc_type == "invoice"
                and e.document.party_id == memo.document.party_id
                and e.amount_cents == memo.amount_cents
            ]
            self.assertTrue(twin, memo.entry_id)

    def test_references_are_unique_per_vendor_apart_from_progress_billing(self):
        counts = collections.Counter(
            (e.document.party_id, e.document.reference) for e in self.led.entries
        )
        repeated = {k for k, v in counts.items() if v > 1}
        self.assertEqual({vid for vid, _ref in repeated}, {PROGRESS_VENDOR})
        self.assertEqual(len(repeated), 4)

    def test_keying_lag_is_continuous_and_reaches_well_past_prompt(self):
        lags = sorted(keying_lag(e) for e in self.led.entries)
        self.assertGreater(max(lags), 40)
        self.assertGreaterEqual(sum(1 for l in lags if l > PROMPT_KEYING_LAG), 20)


class PlantedDuplicateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = default_ap_plan()
        cls.led, cls.man = generate_ap_with_duplicates(CFG, cls.plan)
        cls.by_class = cls.man.by_class()

    def _pair(self, anomaly):
        entries = [self.led.entry(eid) for eid in anomaly.entry_ids]
        self.assertEqual(len(entries), 2, anomaly.anomaly_id)
        entries.sort(key=lambda e: e.posting_date)
        return entries

    def test_counts_and_manifest_ids(self):
        self.assertEqual(len(self.led), CFG.n_entries + sum(self.plan.values()))
        self.assertEqual(len(self.man.anomalies), sum(self.plan.values()))
        for a in self.man.anomalies:
            for eid in a.entry_ids:
                self.assertIn(eid, self.led, a.anomaly_id)
        for cls_name in AP_DUPLICATE_CLASSES:
            self.assertEqual(len(self.by_class[cls_name]), self.plan[cls_name])

    def test_ground_truth_is_the_pair_and_nothing_else(self):
        """Two documents per plant — the original and its duplicate — never
        the vendor's whole account (DECISIONS D-029's rule, applied here)."""
        planted = self.man.all_entry_ids()
        self.assertEqual(len(planted), 2 * len(self.man.anomalies))
        vendors = {self.led.entry(eid).document.party_id for eid in planted}
        for vendor in vendors:
            whole_account = [
                e for e in self.led.entries if e.document.party_id == vendor
            ]
            self.assertGreater(len(whole_account), len(planted))

    def test_exact_rekey(self):
        for a in self.by_class["ap_exact_rekey"]:
            orig, dup = self._pair(a)
            self.assertEqual(orig.document.party_id, dup.document.party_id)
            self.assertEqual(orig.document.reference, dup.document.reference)
            self.assertEqual(orig.document.doc_date, dup.document.doc_date)
            self.assertEqual(orig.amount_cents, dup.amount_cents)
            self.assertNotEqual(orig.posting_date, dup.posting_date)

    def test_cross_period_rekey_lands_in_a_later_period(self):
        for a in self.by_class["ap_cross_period_rekey"]:
            orig, dup = self._pair(a)
            self.assertEqual(orig.document.reference, dup.document.reference)
            self.assertEqual(orig.document.doc_date, dup.document.doc_date)
            self.assertEqual(orig.amount_cents, dup.amount_cents)
            self.assertGreaterEqual((dup.posting_date - orig.posting_date).days, 38)
            self.assertNotEqual(
                period_str(orig.posting_date), period_str(dup.posting_date)
            )

    def test_transposed_reference(self):
        for a in self.by_class["ap_transposed_reference"]:
            orig, dup = self._pair(a)
            self.assertNotEqual(orig.document.reference, dup.document.reference)
            self.assertTrue(
                is_transposition(orig.document.reference, dup.document.reference),
                a.anomaly_id,
            )
            self.assertEqual(orig.document.doc_date, dup.document.doc_date)
            self.assertEqual(orig.amount_cents, dup.amount_cents)
            # The transposed number is not a document that vendor issued.
            same_ref = [
                e
                for e in self.led.entries
                if e.document.party_id == dup.document.party_id
                and e.document.reference == dup.document.reference
            ]
            self.assertEqual(len(same_ref), 1, a.anomaly_id)

    def test_no_reference_match(self):
        for a in self.by_class["ap_no_reference_match"]:
            orig, dup = self._pair(a)
            self.assertEqual(orig.amount_cents, dup.amount_cents)
            self.assertEqual(orig.document.party_id, dup.document.party_id)
            self.assertNotEqual(orig.document.reference, dup.document.reference)
            self.assertFalse(
                is_transposition(orig.document.reference, dup.document.reference),
                a.anomaly_id,
            )
            gap = abs((dup.document.doc_date - orig.document.doc_date).days)
            self.assertLessEqual(gap, 4)

    def test_a_duplicate_is_often_keyed_by_a_different_clerk(self):
        """The mechanism AP duplicate detection exists for: two clerks, one
        invoice. This is also why the AP rules key on the document and the
        GL's R-010 — which requires an identical preparer — cannot stand in."""
        differing = sum(
            1 for a in self.man.anomalies
            if len({self.led.entry(e).preparer_id for e in a.entry_ids}) > 1
        )
        self.assertGreaterEqual(differing, len(self.man.anomalies) // 2)

    def test_plants_are_not_keying_lag_outliers(self):
        """A duplicate is keyed after its own document date, so if the clean
        population left that lag range empty the calendar alone would reveal
        every plant. It does not (D-009's concern, in a different field)."""
        planted = self.man.all_entry_ids()
        clean_lags = [
            keying_lag(e) for e in self.led.entries if e.entry_id not in planted
        ]
        for eid in sorted(planted):
            lag = keying_lag(self.led.entry(eid))
            neighbours = sum(1 for l in clean_lags if l >= lag)
            self.assertGreaterEqual(neighbours, 10, f"{eid} lag {lag}")

    def test_deterministic(self):
        led2, man2 = generate_ap_with_duplicates(CFG, self.plan)
        self.assertEqual(
            canonical_bytes(self.led.to_dict()), canonical_bytes(led2.to_dict())
        )
        self.assertEqual(
            canonical_bytes(self.man.to_dict()), canonical_bytes(man2.to_dict())
        )

    def test_clean_generation_unaffected_by_planting(self):
        """The injector draws from its own stream (D-010), so the clean
        subledger is byte-identical before and after an injection run."""
        before = canonical_bytes(generate_ap_subledger(CFG).to_dict())
        generate_ap_with_duplicates(CFG, self.plan)
        after = canonical_bytes(generate_ap_subledger(CFG).to_dict())
        self.assertEqual(before, after)
        self.assertNotEqual(before, canonical_bytes(self.led.to_dict()))

    def test_different_anomaly_seed_moves_plants_only(self):
        led3, man3 = generate_ap_with_duplicates(CFG, self.plan, anomaly_seed=77)
        self.assertEqual(len(led3), len(self.led))
        self.assertNotEqual(
            canonical_bytes(self.man.to_dict()), canonical_bytes(man3.to_dict())
        )

    def test_manifest_roundtrip(self):
        again = Manifest.from_dict(self.man.to_dict())
        self.assertEqual(
            canonical_bytes(self.man.to_dict()), canonical_bytes(again.to_dict())
        )

    def test_bad_plans_rejected(self):
        with self.assertRaises(ValueError):
            generate_ap_with_duplicates(CFG, {"duplicate_pair": 1})
        with self.assertRaises(ValueError):
            generate_ap_with_duplicates(CFG, {"ap_exact_rekey": -1})

    def test_more_duplicates_than_eligible_originals_is_refused(self):
        with self.assertRaises(ValueError):
            generate_ap_with_duplicates(
                GeneratorConfig(seed=601, n_entries=120), {"ap_exact_rekey": 200}
            )


class TranspositionCandidateTests(unittest.TestCase):
    def test_candidates_are_the_adjacent_digit_swaps(self):
        self.assertEqual(
            transposition_candidates("INV-1234"),
            ["INV-2134", "INV-1324", "INV-1243"],
        )

    def test_repeated_digits_produce_no_candidate(self):
        self.assertEqual(transposition_candidates("INV-4444"), [])

    def test_letters_are_never_swapped(self):
        self.assertEqual(transposition_candidates("AB"), [])


if __name__ == "__main__":
    unittest.main()
