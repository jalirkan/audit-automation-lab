import unittest
from datetime import date

from core.canonical import canonical_bytes
from ledger.anomalies import (
    ANOMALY_CLASSES,
    Manifest,
    default_plan,
    generate_with_anomalies,
)
from ledger.generate import GeneratorConfig, generate

CFG = GeneratorConfig(seed=7, n_entries=1200)


class InjectionBasicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = default_plan()
        cls.led, cls.man = generate_with_anomalies(CFG, cls.plan)

    def test_planted_entry_counts(self):
        # 2 of each class; duplicate/near-duplicate add one new entry each,
        # threshold_shaving adds three per series.
        new_entries = 2 * 8 + 2 * 1 + 2 * 1 + 2 * 3  # singles + dup + near + shaving
        self.assertEqual(len(self.led), CFG.n_entries + new_entries)
        self.assertEqual(len(self.man.anomalies), 2 * len(ANOMALY_CLASSES))

    def test_manifest_ids_exist(self):
        for a in self.man.anomalies:
            for eid in a.entry_ids:
                self.assertIn(eid, self.led, f"{a.anomaly_id} references missing {eid}")

    def test_ids_follow_posting_date_order(self):
        dates = [e.posting_date for e in self.led.entries]
        self.assertEqual(dates, sorted(dates))
        for i, e in enumerate(self.led.entries, start=1):
            self.assertEqual(e.entry_id, f"JE-{i:06d}")

    def test_by_class_counts_match_plan(self):
        by_class = self.man.by_class()
        for cls_name in ANOMALY_CLASSES:
            self.assertEqual(len(by_class[cls_name]), self.plan[cls_name], cls_name)

    def test_deterministic(self):
        led2, man2 = generate_with_anomalies(CFG, self.plan)
        self.assertEqual(
            canonical_bytes(self.led.to_dict()), canonical_bytes(led2.to_dict())
        )
        self.assertEqual(
            canonical_bytes(self.man.to_dict()), canonical_bytes(man2.to_dict())
        )

    def test_clean_generation_unaffected_by_planting(self):
        """The injector uses its own derived stream (DECISIONS D-010): a clean
        generate() before and after injection is byte-identical, and differs
        from the planted ledger."""
        clean_a = canonical_bytes(generate(CFG).to_dict())
        generate_with_anomalies(CFG, self.plan)
        clean_b = canonical_bytes(generate(CFG).to_dict())
        self.assertEqual(clean_a, clean_b)
        self.assertNotEqual(clean_a, canonical_bytes(self.led.to_dict()))

    def test_different_anomaly_seed_moves_plants_only(self):
        led3, man3 = generate_with_anomalies(CFG, self.plan, anomaly_seed=99)
        self.assertNotEqual(
            canonical_bytes(self.man.to_dict()), canonical_bytes(man3.to_dict())
        )
        self.assertEqual(len(led3), len(self.led))

    def test_manifest_roundtrip(self):
        again = Manifest.from_dict(self.man.to_dict())
        self.assertEqual(
            canonical_bytes(self.man.to_dict()), canonical_bytes(again.to_dict())
        )

    def test_bad_plans_rejected(self):
        with self.assertRaises(ValueError):
            generate_with_anomalies(CFG, {"no_such_class": 1})
        with self.assertRaises(ValueError):
            generate_with_anomalies(CFG, {"self_approval": -1})


class PlantedPropertyTests(unittest.TestCase):
    """Each planted class actually has the property the scenario claims —
    the manifest is only ground truth if the plants are real."""

    @classmethod
    def setUpClass(cls):
        cls.plan = default_plan()
        cls.led, cls.man = generate_with_anomalies(CFG, cls.plan)
        cls.threshold = CFG.approval_threshold_cents
        cls.by_class = cls.man.by_class()

    def _entries(self, anomaly):
        return [self.led.entry(eid) for eid in anomaly.entry_ids]

    def test_late_round_dollar(self):
        for a in self.by_class["late_round_dollar"]:
            (e,) = self._entries(a)
            self.assertEqual(e.amount_cents % 100_000, 0)
            self.assertEqual(e.posting_date, date(2025, 12, 31))
            self.assertEqual(e.source, "GL")

    def test_post_close_entry(self):
        for a in self.by_class["post_close_entry"]:
            (e,) = self._entries(a)
            self.assertGreater(e.posting_date, CFG.end)
            self.assertEqual(e.effective_date, CFG.end)

    def test_self_approval(self):
        for a in self.by_class["self_approval"]:
            (e,) = self._entries(a)
            self.assertEqual(e.approver_id, e.preparer_id)
            self.assertGreaterEqual(e.amount_cents, self.threshold)

    def test_duplicate_pair(self):
        for a in self.by_class["duplicate_pair"]:
            orig, dup = self._entries(a)
            self.assertNotEqual(orig.entry_id, dup.entry_id)
            self.assertEqual(orig.amount_cents, dup.amount_cents)
            self.assertEqual(orig.account_ids, dup.account_ids)
            self.assertEqual(orig.description, dup.description)
            self.assertEqual(orig.preparer_id, dup.preparer_id)
            self.assertNotEqual(orig.posting_date, dup.posting_date)

    def test_near_duplicate(self):
        for a in self.by_class["near_duplicate"]:
            orig, near = self._entries(a)
            self.assertEqual(orig.account_ids, near.account_ids)
            ratio = near.amount_cents / orig.amount_cents
            self.assertGreater(ratio, 1.004)
            self.assertLess(ratio, 1.012)
            self.assertTrue(near.description.endswith("(resubmitted)"))

    def test_threshold_shaving(self):
        for a in self.by_class["threshold_shaving"]:
            entries = self._entries(a)
            self.assertEqual(len(entries), 3)
            preparers = {e.preparer_id for e in entries}
            self.assertEqual(len(preparers), 1)
            for e in entries:
                self.assertLess(e.amount_cents, self.threshold)
                self.assertGreaterEqual(e.amount_cents, self.threshold - 60_100)
                self.assertIsNone(e.approver_id)

    def test_dormant_reactivation(self):
        inactive = set(self.led.coa.inactive_ids())
        for a in self.by_class["dormant_reactivation"]:
            (e,) = self._entries(a)
            touched = {l.account_id for l in e.lines}
            self.assertTrue(touched & inactive, e.entry_id)

    def test_unbalanced_entry(self):
        for a in self.by_class["unbalanced_entry"]:
            (e,) = self._entries(a)
            self.assertFalse(e.is_balanced)

    def test_missing_description(self):
        for a in self.by_class["missing_description"]:
            (e,) = self._entries(a)
            self.assertEqual(e.description, "")

    def test_weekend_manual(self):
        for a in self.by_class["weekend_manual"]:
            (e,) = self._entries(a)
            self.assertGreaterEqual(e.posting_date.weekday(), 5)
            self.assertTrue(e.preparer_id.startswith("P-"))
            self.assertEqual(e.source, "GL")

    def test_unusual_pairing_pairs_are_distinct_and_unique(self):
        from ledger.anomalies import UNUSUAL_PAIRS

        planted_pairs = []
        for a in self.by_class["unusual_pairing"]:
            (e,) = self._entries(a)
            pair = (e.debit_account_ids[0], e.credit_account_ids[0])
            self.assertIn(pair, UNUSUAL_PAIRS)
            planted_pairs.append(pair)
        # Each instance uses a different pair, and each planted pair occurs
        # exactly once in the whole population.
        self.assertEqual(len(planted_pairs), len(set(planted_pairs)))
        for pair in planted_pairs:
            hits = [
                e.entry_id
                for e in self.led.entries
                if pair[0] in e.debit_account_ids and pair[1] in e.credit_account_ids
            ]
            self.assertEqual(len(hits), 1, pair)

    def test_unusual_pairing_count_capped(self):
        with self.assertRaises(ValueError):
            generate_with_anomalies(CFG, {"unusual_pairing": 4})


if __name__ == "__main__":
    unittest.main()
