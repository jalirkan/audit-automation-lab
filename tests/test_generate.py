import unittest
from datetime import date

from core.canonical import canonical_bytes
from core.dates import holidays_for_range, is_business_day
from ledger.generate import (
    GeneratorConfig,
    MANUAL_SOURCES,
    generate,
)
from ledger.model import Ledger


CFG = GeneratorConfig(seed=42, n_entries=900)


class DeterminismTests(unittest.TestCase):
    def test_same_seed_byte_identical(self):
        a = canonical_bytes(generate(CFG).to_dict())
        b = canonical_bytes(generate(CFG).to_dict())
        self.assertEqual(a, b)

    def test_csv_deterministic(self):
        self.assertEqual(generate(CFG).entries_csv(), generate(CFG).entries_csv())

    def test_different_seed_differs(self):
        other = GeneratorConfig(seed=43, n_entries=900)
        self.assertNotEqual(
            canonical_bytes(generate(CFG).to_dict()),
            canonical_bytes(generate(other).to_dict()),
        )

    def test_roundtrip(self):
        led = generate(CFG)
        again = Ledger.from_dict(led.to_dict())
        self.assertEqual(canonical_bytes(led.to_dict()), canonical_bytes(again.to_dict()))


class CleanPopulationTests(unittest.TestCase):
    """Structural guarantees of the clean (no-anomaly) population. These are
    the documented base rates DECISIONS D-008 refers to."""

    @classmethod
    def setUpClass(cls):
        cls.led = generate(CFG)
        cls.holidays = holidays_for_range(CFG.start, CFG.end)
        cls.threshold = CFG.approval_threshold_cents

    def test_entry_count_and_ids(self):
        self.assertEqual(len(self.led), CFG.n_entries)
        for i, e in enumerate(self.led.entries, start=1):
            self.assertEqual(e.entry_id, f"JE-{i:06d}")
        dates = [e.posting_date for e in self.led.entries]
        self.assertEqual(dates, sorted(dates))

    def test_all_entries_balanced(self):
        for e in self.led.entries:
            self.assertTrue(e.is_balanced, e.entry_id)

    def test_all_descriptions_present(self):
        for e in self.led.entries:
            self.assertGreaterEqual(len(e.description), 10, e.entry_id)

    def test_approvals_complete_and_segregated(self):
        for e in self.led.entries:
            required = e.source == "GL" or e.amount_cents >= self.threshold
            if required:
                self.assertIsNotNone(e.approver_id, e.entry_id)
            if e.approver_id is not None:
                self.assertNotEqual(e.approver_id, e.preparer_id, e.entry_id)
                self.assertTrue(e.approver_id.startswith("A-"), e.entry_id)

    def test_no_postings_to_inactive_accounts(self):
        inactive = set(self.led.coa.inactive_ids())
        self.assertTrue(inactive)  # the default chart ships dormant accounts
        for e in self.led.entries:
            for line in e.lines:
                self.assertNotIn(line.account_id, inactive, e.entry_id)

    def test_manual_sources_post_on_business_days_only(self):
        for e in self.led.entries:
            if e.source in MANUAL_SOURCES:
                self.assertTrue(
                    is_business_day(e.posting_date, self.holidays), e.entry_id
                )

    def test_documented_benign_round_dollar_base_rate(self):
        """Base rate, pinned: the only exact-multiple-of-$1,000 amounts in a
        clean year are the 12 monthly rent entries; the only other .00
        amounts are the 12 insurance premiums. Stochastic amounts always
        carry non-zero cents by construction."""
        mult_1000 = [e for e in self.led.entries if e.amount_cents % 100_000 == 0]
        self.assertEqual(len(mult_1000), 12)
        for e in mult_1000:
            self.assertTrue(e.description.startswith("Monthly office rent"), e.entry_id)

        whole_dollar = [e for e in self.led.entries if e.amount_cents % 100 == 0]
        self.assertEqual(len(whole_dollar), 24)  # 12 rent + 12 insurance

    def test_documented_benign_weekend_base_rate(self):
        """Base rate, pinned: weekend postings in a clean FY2025 are exactly
        the system month-end batch (depreciation + interest) for May, August
        and November — 6 entries, all source SYS, none by a human user."""
        weekend = [e for e in self.led.entries if e.posting_date.weekday() >= 5]
        self.assertEqual(len(weekend), 6)
        for e in weekend:
            self.assertEqual(e.source, "SYS", e.entry_id)
            self.assertEqual(e.preparer_id, "SYS-BATCH", e.entry_id)

    def test_year_end_window_share_is_bounded(self):
        """Month-end weighting concentrates entries at period ends, but the
        final-5-business-day window of the fiscal year stays under 8% of the
        population — the documented benign period-end pressure."""
        from core.dates import last_n_business_days

        window = last_n_business_days(CFG.end, 5, self.holidays)
        in_window = [e for e in self.led.entries if e.posting_date in window]
        self.assertGreater(len(in_window), 0)
        self.assertLess(len(in_window), 0.08 * len(self.led.entries))

    def test_payroll_schedule(self):
        pay = [e for e in self.led.entries if e.source == "PAY"]
        self.assertEqual(len(pay), 26)  # biweekly Fridays from 2025-01-03
        for e in pay:
            self.assertEqual(len(e.lines), 3)
            self.assertTrue(e.is_balanced)
            # 2025-07-04 payday is a holiday Friday: shifts to Thursday 07-03.
        self.assertIn(date(2025, 7, 3), [e.posting_date for e in pay])

    def test_config_too_small_raises(self):
        with self.assertRaises(ValueError):
            generate(GeneratorConfig(seed=1, n_entries=10))


if __name__ == "__main__":
    unittest.main()
