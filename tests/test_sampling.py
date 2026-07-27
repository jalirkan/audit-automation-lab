import unittest

from core.canonical import canonical_bytes
from core.stats import binom_cdf, hypergeom_cdf
from sampling.attribute import (
    OUTCOME_EXCEPTION,
    OUTCOME_INCONCLUSIVE,
    OUTCOME_SUPPORTS,
    attribute_sample_size,
    evaluate_attribute_sample,
    upper_deviation_limit,
)


class SampleSizeTests(unittest.TestCase):
    def test_classic_anchors_recomputed(self):
        """5%/5%/0 -> 59 and 10%/10%/0 -> 22, derived from (1-p)^n <= risk —
        agreement with the published tables is a test of the math, not a
        source of it (DECISIONS D-005)."""
        r = attribute_sample_size(0.05, 0.05)
        self.assertEqual((r.n, r.allowance), (59, 0))
        self.assertLessEqual(r.achieved_risk, 0.05)
        # one fewer would breach the risk
        self.assertGreater(binom_cdf(0, 58, 0.05), 0.05)

        r = attribute_sample_size(0.10, 0.10)
        self.assertEqual((r.n, r.allowance), (22, 0))

    def test_expected_deviations_anchor(self):
        # 5% tolerable, 5% risk, 1% expected: n=93 with allowance 1.
        r = attribute_sample_size(0.05, 0.05, expected_rate=0.01)
        self.assertEqual((r.n, r.allowance), (93, 1))
        self.assertLessEqual(binom_cdf(1, 93, 0.05), 0.05)

    def test_monotonicity(self):
        base = attribute_sample_size(0.05, 0.05).n
        self.assertGreater(attribute_sample_size(0.03, 0.05).n, base)
        self.assertGreater(attribute_sample_size(0.05, 0.01).n, base)
        self.assertGreater(
            attribute_sample_size(0.05, 0.05, expected_rate=0.02).n, base
        )

    def test_finite_population_reduces_n(self):
        fin = attribute_sample_size(0.05, 0.05, population=500)
        inf = attribute_sample_size(0.05, 0.05)
        self.assertLess(fin.n, inf.n)
        self.assertGreater(fin.n, 40)
        self.assertEqual(fin.method, "hypergeometric")
        # verify the defining condition directly
        k_pop = 25  # ceil(0.05 * 500)
        self.assertLessEqual(hypergeom_cdf(0, 500, k_pop, fin.n), 0.05)
        self.assertGreater(hypergeom_cdf(0, 500, k_pop, fin.n - 1), 0.05)

    def test_infeasible_raises(self):
        with self.assertRaises(ValueError):
            attribute_sample_size(0.05, 0.05, expected_rate=0.05)
        with self.assertRaises(ValueError):
            attribute_sample_size(0.2, 0.05, expected_rate=0.15, population=10)

    def test_serializes(self):
        r = attribute_sample_size(0.05, 0.05)
        self.assertEqual(
            canonical_bytes(r.to_dict()),
            canonical_bytes(attribute_sample_size(0.05, 0.05).to_dict()),
        )


class UpperDeviationLimitTests(unittest.TestCase):
    def test_zero_deviations_closed_form(self):
        """k=0: UDL solves (1-p)^n = risk, so p = 1 - risk^(1/n)."""
        r = upper_deviation_limit(59, 0, 0.05)
        self.assertAlmostEqual(r.udl, 1 - 0.05 ** (1 / 59), places=6)
        r = upper_deviation_limit(60, 0, 0.05)
        self.assertAlmostEqual(r.udl, 0.0487, places=3)

    def test_udl_exceeds_sample_rate_and_grows_with_k(self):
        prev = 0.0
        for k in range(0, 5):
            r = upper_deviation_limit(60, k, 0.05)
            self.assertGreater(r.udl, r.sample_rate)
            self.assertGreater(r.udl, prev)
            prev = r.udl

    def test_all_deviations_is_certainty(self):
        self.assertEqual(upper_deviation_limit(10, 10, 0.05).udl, 1.0)

    def test_defining_condition_holds(self):
        r = upper_deviation_limit(60, 2, 0.05)
        self.assertLessEqual(binom_cdf(2, 60, r.udl), 0.05)
        self.assertGreater(binom_cdf(2, 60, r.udl - 1e-6), 0.05 - 1e-9)

    def test_hypergeometric_bound_at_most_binomial(self):
        fin = upper_deviation_limit(60, 1, 0.05, population=400)
        inf = upper_deviation_limit(60, 1, 0.05)
        self.assertLessEqual(fin.udl, inf.udl + 1e-9)
        self.assertEqual(fin.method, "hypergeometric")
        k = fin.population_deviations_bound
        self.assertLessEqual(hypergeom_cdf(1, 400, k, 60), 0.05)
        self.assertGreater(hypergeom_cdf(1, 400, k - 1, 60), 0.05)

    def test_validation(self):
        with self.assertRaises(ValueError):
            upper_deviation_limit(0, 0, 0.05)
        with self.assertRaises(ValueError):
            upper_deviation_limit(10, 11, 0.05)
        with self.assertRaises(ValueError):
            upper_deviation_limit(10, 1, 0.05, population=5)


class EvaluationTests(unittest.TestCase):
    def test_three_outcomes(self):
        clean = evaluate_attribute_sample(60, 0, 0.05, 0.05)
        self.assertEqual(clean.outcome, OUTCOME_SUPPORTS)

        dirty = evaluate_attribute_sample(60, 5, 0.05, 0.05)
        self.assertEqual(dirty.outcome, OUTCOME_EXCEPTION)

        thin = evaluate_attribute_sample(60, 1, 0.05, 0.05)
        self.assertEqual(thin.outcome, OUTCOME_INCONCLUSIVE)
        self.assertIn("cannot support reliance", thin.reason)

    def test_boundary_supports(self):
        # n=59, k=0 at 5% risk: UDL just under 5% -> supports.
        r = evaluate_attribute_sample(59, 0, 0.05, 0.05)
        self.assertEqual(r.outcome, OUTCOME_SUPPORTS)

    def test_serializes_deterministically(self):
        a = evaluate_attribute_sample(60, 1, 0.05, 0.05).to_dict()
        b = evaluate_attribute_sample(60, 1, 0.05, 0.05).to_dict()
        self.assertEqual(canonical_bytes(a), canonical_bytes(b))


if __name__ == "__main__":
    unittest.main()
