import unittest
from datetime import date

from continuous.periods import (
    combine_batches,
    monthly_batches,
    period_of,
    split_baseline,
    sub_ledger,
)
from ledger.generate import GeneratorConfig, generate
from tests.test_rules import mk_entry, mk_ledger


class PeriodBasisTests(unittest.TestCase):
    """The batching basis is posting date, deliberately and by test: an
    entry posted in January against a December effective date belongs to
    January's batch, because that is the month a monitor would first see it
    (and the lag is exactly what R-002 exists to notice)."""

    def test_posting_date_decides_not_effective_date(self):
        e = mk_entry(
            "JE-000001", date(2026, 1, 6), effective=date(2025, 12, 31)
        )
        self.assertEqual(period_of(e), "2026-01")
        self.assertEqual(e.period, "2025-12")  # the effective-date property


class BatchingTests(unittest.TestCase):
    def setUp(self):
        self.entries = [
            mk_entry("JE-000001", date(2025, 1, 6)),
            mk_entry("JE-000002", date(2025, 1, 31)),
            mk_entry("JE-000003", date(2025, 2, 3)),
            mk_entry("JE-000004", date(2025, 4, 1)),
        ]
        self.led = mk_ledger(self.entries)

    def test_batches_are_a_partition_in_period_order(self):
        batches = monthly_batches(self.led)
        self.assertEqual([b.period for b in batches],
                         ["2025-01", "2025-02", "2025-04"])
        self.assertEqual([len(b) for b in batches], [2, 1, 1])
        # Concatenating the batches reproduces the parent exactly: batching
        # partitions, it never reorders or drops.
        rebuilt = [e.entry_id for b in batches for e in b.ledger.entries]
        self.assertEqual(rebuilt, [e.entry_id for e in self.led.entries])

    def test_batch_carries_chart_users_and_annotated_meta(self):
        batch = monthly_batches(self.led)[0]
        self.assertEqual(batch.ledger.coa.ids(), self.led.coa.ids())
        self.assertEqual(batch.ledger.users, self.led.users)
        # Metadata a rule reads survives the slice...
        self.assertEqual(
            batch.ledger.meta["fiscal_year_end"], self.led.meta["fiscal_year_end"]
        )
        # ...and the slice cannot claim the parent's size.
        self.assertEqual(batch.ledger.meta["n_entries"], 2)
        self.assertEqual(batch.ledger.meta["batch"]["parent_n_entries"], 4)
        self.assertEqual(batch.ledger.meta["batch"]["period"], "2025-01")

    def test_sub_ledger_does_not_mutate_parent_meta(self):
        sub_ledger(self.led, self.entries[:1], "2025-01")
        self.assertNotIn("batch", self.led.meta)
        self.assertEqual(self.led.meta["fiscal_year_end"], "2025-12-31")

    def test_profile_of_a_batch_describes_the_batch(self):
        batch = monthly_batches(self.led)[0]
        profile = batch.profile()
        self.assertEqual(profile.n_entries, 2)
        self.assertEqual(profile.date_min, "2025-01-06")
        self.assertEqual(profile.date_max, "2025-01-31")

    def test_combine_batches_spans_the_window(self):
        batches = monthly_batches(self.led)
        combined = combine_batches(self.led, batches[:2])
        self.assertEqual(len(combined), 3)
        self.assertEqual(combined.meta["batch"]["period"], "2025-01..2025-02")

    def test_split_baseline(self):
        batches = monthly_batches(self.led)
        baseline, tested = split_baseline(batches, 2)
        self.assertEqual([b.period for b in baseline], ["2025-01", "2025-02"])
        self.assertEqual([b.period for b in tested], ["2025-04"])
        with self.assertRaises(ValueError):
            split_baseline(batches, 0)


class GeneratedLedgerBatchingTests(unittest.TestCase):
    def test_a_fiscal_year_batches_into_twelve_months(self):
        led = generate(GeneratorConfig(seed=42, n_entries=1200))
        batches = monthly_batches(led)
        self.assertEqual(len(batches), 12)
        self.assertEqual(sum(len(b) for b in batches), len(led))
        self.assertEqual([b.period for b in batches], sorted(b.period for b in batches))

    def test_batching_is_deterministic(self):
        led = generate(GeneratorConfig(seed=42, n_entries=600))
        a = [(b.period, [e.entry_id for e in b.ledger.entries])
             for b in monthly_batches(led)]
        b = [(x.period, [e.entry_id for e in x.ledger.entries])
             for x in monthly_batches(led)]
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
