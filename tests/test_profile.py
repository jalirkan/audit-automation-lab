import unittest
from datetime import date

from analytics.profile import PopulationProfile, nearest_rank_deciles
from core.canonical import canonical_bytes
from tests.test_rules import mk_entry, mk_ledger


class DecileTests(unittest.TestCase):
    def test_nearest_rank_pinned(self):
        values = list(range(1, 12))  # 1..11
        d = nearest_rank_deciles(values)
        self.assertEqual(d[0], 1)
        self.assertEqual(d[5], 6)
        self.assertEqual(d[10], 11)
        self.assertEqual(nearest_rank_deciles([]), {})
        self.assertEqual(nearest_rank_deciles([7])[0], 7)
        self.assertEqual(nearest_rank_deciles([7])[10], 7)


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.led = mk_ledger(
            [
                mk_entry("JE-000001", date(2025, 3, 10), amount=100_00, source="AP",
                         approver=None),
                mk_entry("JE-000002", date(2025, 3, 11), amount=200_00, source="GL"),
                mk_entry("JE-000003", date(2025, 4, 6), amount=300_00, source="GL",
                         preparer="P-02"),  # a Sunday
                mk_entry("JE-000004", date(2025, 4, 7), amount=12_000_00, source="REV",
                         approver=None),  # above threshold, missing approval
            ]
        )
        self.profile = PopulationProfile.build(self.led)

    def test_counts(self):
        p = self.profile
        self.assertEqual(p.n_entries, 4)
        self.assertEqual(p.n_lines, 8)
        self.assertEqual(p.by_source, {"AP": 1, "GL": 2, "REV": 1})
        self.assertEqual(p.by_preparer, {"P-01": 3, "P-02": 1})
        self.assertEqual(p.by_weekday[6], 1)  # the Sunday entry
        self.assertEqual(p.by_month, {"2025-03": 2, "2025-04": 2})
        self.assertEqual(p.date_min, "2025-03-10")
        self.assertEqual(p.date_max, "2025-04-07")

    def test_approval_tallies(self):
        # GL x2 and the 12k REV entry require approval; the REV one lacks it.
        self.assertEqual(self.profile.n_requiring_approval, 3)
        self.assertEqual(self.profile.n_missing_approval, 1)

    def test_top_amounts_and_deciles(self):
        self.assertEqual(self.profile.top_amounts[0]["entry_id"], "JE-000004")
        self.assertEqual(self.profile.amount_deciles[0], 100_00)
        self.assertEqual(self.profile.amount_deciles[10], 12_000_00)

    def test_deterministic_serialization(self):
        a = canonical_bytes(PopulationProfile.build(self.led).to_dict())
        b = canonical_bytes(PopulationProfile.build(self.led).to_dict())
        self.assertEqual(a, b)

    def test_generated_ledger_profile(self):
        from ledger.generate import GeneratorConfig, generate

        led = generate(GeneratorConfig(seed=42, n_entries=900))
        p = PopulationProfile.build(led)
        self.assertEqual(p.n_entries, 900)
        self.assertEqual(sum(p.by_source.values()), 900)
        self.assertEqual(p.n_missing_approval, 0)
        canonical_bytes(p.to_dict())  # JSONable


if __name__ == "__main__":
    unittest.main()
