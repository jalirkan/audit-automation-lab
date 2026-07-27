import random
import unittest

from analytics.benford import (
    CONCLUSION_CONFORMING,
    CONCLUSION_INCONCLUSIVE,
    CONCLUSION_NONCONFORMING,
    benford_first_expected,
    benford_second_expected,
    first_digit,
    first_digit_test,
    second_digit,
    second_digit_test,
)
from core.canonical import canonical_bytes


def log_uniform_sample(n=2000, lo_exp=2.0, hi_exp=6.0):
    """Amounts whose log10 is uniform: Benford-conforming by construction."""
    out = []
    for i in range(n):
        u = lo_exp + (hi_exp - lo_exp) * i / (n - 1)
        out.append(int(round(10 ** u)))
    return out


class DigitExtractionTests(unittest.TestCase):
    def test_first_and_second(self):
        self.assertEqual(first_digit(123456), 1)
        self.assertEqual(first_digit(9), 9)
        self.assertEqual(second_digit(90), 0)
        self.assertEqual(second_digit(1234), 2)
        self.assertIsNone(second_digit(7))
        with self.assertRaises(ValueError):
            first_digit(0)

    def test_expected_distributions_sum_to_one(self):
        self.assertAlmostEqual(sum(benford_first_expected().values()), 1.0, places=12)
        self.assertAlmostEqual(sum(benford_second_expected().values()), 1.0, places=12)
        self.assertAlmostEqual(benford_first_expected()[1], 0.30103, places=5)


class ConformingDataTests(unittest.TestCase):
    def test_log_uniform_passes_first_digit(self):
        res = first_digit_test(log_uniform_sample())
        self.assertTrue(res.applicable)
        self.assertEqual(res.conclusion, CONCLUSION_CONFORMING)
        self.assertLess(res.mad, 0.012)

    def test_log_uniform_passes_second_digit(self):
        res = second_digit_test(log_uniform_sample())
        self.assertTrue(res.applicable)
        self.assertEqual(res.conclusion, CONCLUSION_CONFORMING)

    def test_every_digit_measurement_carries_interval_and_n(self):
        res = first_digit_test(log_uniform_sample())
        self.assertEqual(len(res.digit_measurements), 9)
        for d, m in res.digit_measurements.items():
            self.assertEqual(m.n, res.n)
            self.assertEqual(m.method, "wilson")
            self.assertIn("n=", m.render())

    def test_result_serializes_canonically(self):
        res = first_digit_test(log_uniform_sample())
        self.assertEqual(
            canonical_bytes(res.to_dict()), canonical_bytes(res.to_dict())
        )


class NonConformingDataTests(unittest.TestCase):
    def test_uniform_amounts_fail(self):
        # Linear-uniform across three orders of magnitude: wide enough to be
        # applicable, but 90% of the mass sits in the top decade, so first
        # digits come out near-uniform instead of logarithmic.
        rng = random.Random(1)
        amounts = [rng.randrange(10_000, 10_000_000) for _ in range(3000)]
        res = first_digit_test(amounts)
        self.assertTrue(res.applicable)
        self.assertEqual(res.conclusion, CONCLUSION_NONCONFORMING)
        self.assertGreater(res.mad, 0.015)
        self.assertLess(res.p_value, 0.001)

    def test_conclusion_reason_names_the_decider(self):
        rng = random.Random(2)
        amounts = [rng.randrange(10_000, 10_000_000) for _ in range(3000)]
        res = first_digit_test(amounts)
        self.assertIn("MAD", res.conclusion_reason)
        self.assertIn("does not decide", res.conclusion_reason)


class ApplicabilityGuardTests(unittest.TestCase):
    def test_small_population_refuses(self):
        res = first_digit_test(log_uniform_sample(n=50))
        self.assertFalse(res.applicable)
        self.assertIsNone(res.p_value)
        self.assertEqual(res.conclusion, CONCLUSION_INCONCLUSIVE)
        self.assertIn("minimum", res.refusal_reason)

    def test_narrow_span_refuses(self):
        rng = random.Random(3)
        amounts = [rng.randrange(50_000, 60_000) for _ in range(2000)]
        res = first_digit_test(amounts)
        self.assertFalse(res.applicable)
        self.assertIn("orders of magnitude", res.refusal_reason)

    def test_assigned_amounts_refuse(self):
        rng = random.Random(4)
        # A contractual amount repeated heavily inside otherwise-wide data.
        amounts = [250_000] * 400 + [rng.randrange(1_000, 10_000_000) for _ in range(1600)]
        res = first_digit_test(amounts)
        self.assertFalse(res.applicable)
        self.assertIn("assigned or contractual", res.refusal_reason)

    def test_refusal_carries_no_p_value_or_mad(self):
        res = first_digit_test([100] * 10)
        self.assertIsNone(res.p_value)
        self.assertIsNone(res.mad)
        self.assertIn("false precision", res.conclusion_reason)


class LedgerSmokeTests(unittest.TestCase):
    def test_generated_ledger_runs_and_reports(self):
        from analytics.benford import benford_for_ledger
        from ledger.generate import GeneratorConfig, generate

        led = generate(GeneratorConfig(seed=42, n_entries=900))
        results = benford_for_ledger(led)
        for name in ("first_digit", "second_digit"):
            res = results[name]
            self.assertTrue(res.applicable, res.refusal_reason)
            self.assertIn(
                res.conclusion,
                (
                    CONCLUSION_CONFORMING,
                    CONCLUSION_NONCONFORMING,
                    CONCLUSION_INCONCLUSIVE,
                ),
            )
            self.assertIsNotNone(res.p_value)
            # deterministic
            again = benford_for_ledger(led)[name]
            self.assertEqual(
                canonical_bytes(res.to_dict()), canonical_bytes(again.to_dict())
            )


if __name__ == "__main__":
    unittest.main()
