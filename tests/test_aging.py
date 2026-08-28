import unittest
from datetime import date

from continuous.aging import (
    DEFAULT_BUCKETS,
    age_exceptions,
    bucket_label,
    bucket_labels,
    flatten_flags,
    months_between,
)
from core.canonical import canonical_bytes
from ledger.generate import GeneratorConfig, generate
from rules.base import Flag
from rules.registry import default_rules, evaluate_all
from tests.test_rules import mk_entry, mk_ledger


class PeriodArithmeticTests(unittest.TestCase):
    def test_months_between_crosses_years(self):
        self.assertEqual(months_between("2025-01", "2025-04"), 3)
        self.assertEqual(months_between("2025-11", "2026-02"), 3)
        self.assertEqual(months_between("2025-06", "2025-06"), 0)
        self.assertEqual(months_between("2026-01", "2025-12"), -1)

    def test_buckets_have_an_open_ended_top(self):
        self.assertEqual(bucket_labels(), ("0", "1", "2", "3+"))
        self.assertEqual(bucket_label(0), "0")
        self.assertEqual(bucket_label(2), "2")
        self.assertEqual(bucket_label(3), "3+")
        self.assertEqual(bucket_label(97), "3+")


class HandComputedAgingTests(unittest.TestCase):
    """Five entries across four months, six flags, reporting period
    2025-05:

    JE-1 posted 2025-01 -> age 4 -> bucket 3+   (flagged by R-A and R-B)
    JE-2 posted 2025-03 -> age 2 -> bucket 2    (R-A)
    JE-3 posted 2025-05 -> age 0 -> bucket 0    (R-A)
    JE-4 posted 2025-04 -> age 1 -> bucket 1    (R-B)
    JE-5 posted 2025-06 -> not yet visible as of 2025-05

    by_bucket: {0:1, 1:1, 2:1, 3+:2}; six flags in, five aged, one deferred.
    """

    def setUp(self):
        self.led = mk_ledger(
            [
                mk_entry("JE-000001", date(2025, 1, 9)),
                mk_entry("JE-000002", date(2025, 3, 4)),
                mk_entry("JE-000003", date(2025, 5, 20)),
                mk_entry("JE-000004", date(2025, 4, 15)),
                mk_entry("JE-000005", date(2025, 6, 2)),
            ]
        )
        self.flags = [
            Flag("R-A", "JE-000001", "x"),
            Flag("R-B", "JE-000001", "x"),
            Flag("R-A", "JE-000002", "x"),
            Flag("R-A", "JE-000003", "x"),
            Flag("R-B", "JE-000004", "x"),
            Flag("R-B", "JE-000005", "x"),
        ]

    def test_hand_computed_schedule(self):
        s = age_exceptions(self.flags, self.led, as_of_period="2025-05")
        self.assertEqual(s.n_exceptions, 5)
        self.assertEqual(s.n_not_yet_posted, 1)
        self.assertEqual(s.by_bucket, {"0": 1, "1": 1, "2": 1, "3+": 2})
        self.assertEqual(s.max_age_periods, 4)
        self.assertEqual(
            s.by_rule["R-A"], {"0": 1, "1": 0, "2": 1, "3+": 1}
        )
        self.assertEqual(
            s.by_rule["R-B"], {"0": 0, "1": 1, "2": 0, "3+": 1}
        )

    def test_oldest_is_ordered_and_stable(self):
        s = age_exceptions(self.flags, self.led, as_of_period="2025-05")
        oldest = s.oldest()
        self.assertEqual(
            [(a.rule_id, a.entry_id, a.age_periods) for a in oldest],
            [
                ("R-A", "JE-000001", 4),
                ("R-B", "JE-000001", 4),
                ("R-A", "JE-000002", 2),
                ("R-B", "JE-000004", 1),
                ("R-A", "JE-000003", 0),
            ],
        )
        self.assertEqual(len(s.oldest(limit=2)), 2)

    def test_as_of_defaults_to_the_last_period_in_the_ledger(self):
        """Nothing here reads a clock: the reporting period comes from the
        data, so a schedule is reproducible years later (D-019)."""
        s = age_exceptions(self.flags, self.led)
        self.assertEqual(s.as_of_period, "2025-06")
        self.assertEqual(s.n_not_yet_posted, 0)
        self.assertEqual(s.n_exceptions, 6)

    def test_earlier_as_of_defers_more(self):
        s = age_exceptions(self.flags, self.led, as_of_period="2025-03")
        self.assertEqual(s.n_exceptions, 3)   # JE-1 x2, JE-2
        self.assertEqual(s.n_not_yet_posted, 3)

    def test_serializes_canonically_and_states_its_basis(self):
        d = age_exceptions(self.flags, self.led, as_of_period="2025-05").to_dict()
        canonical_bytes(d)
        self.assertIn("no disposition data exists", d["basis"])
        self.assertEqual(d["buckets"], list(bucket_labels(DEFAULT_BUCKETS)))


class BatteryAgingTests(unittest.TestCase):
    def test_ages_a_real_battery_run_deterministically(self):
        led = generate(GeneratorConfig(seed=42, n_entries=900))
        results = evaluate_all(led, rules=default_rules())
        flags = flatten_flags(results)
        self.assertGreater(len(flags), 0)
        a = age_exceptions(flags, led)
        b = age_exceptions(flags, led)
        self.assertEqual(canonical_bytes(a.to_dict()), canonical_bytes(b.to_dict()))
        # Every flag is either aged or explicitly deferred; none vanish.
        self.assertEqual(a.n_exceptions + a.n_not_yet_posted, len(flags))
        self.assertEqual(sum(a.by_bucket.values()), a.n_exceptions)


if __name__ == "__main__":
    unittest.main()
