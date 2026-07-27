import unittest

from core.stats import (
    Decision,
    Measurement,
    OUTCOME_EXCEPTION,
    OUTCOME_INCONCLUSIVE,
    OUTCOME_PASS,
    binom_cdf,
    binom_pmf,
    chi_square_sf,
    decide,
    hypergeom_cdf,
    hypergeom_pmf,
    proportion,
    wilson_interval,
    z_value,
)


class WilsonTests(unittest.TestCase):
    def test_z_value(self):
        self.assertAlmostEqual(z_value(0.95), 1.959964, places=5)

    def test_one_in_eight(self):
        lo, hi = wilson_interval(1, 8)
        self.assertAlmostEqual(lo, 0.0224, places=3)
        self.assertAlmostEqual(hi, 0.4709, places=3)

    def test_zero_of_twenty_has_width(self):
        lo, hi = wilson_interval(0, 20)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 3.8415 / 23.8415, places=3)

    def test_n_zero_is_uninformative(self):
        self.assertEqual(wilson_interval(0, 0), (0.0, 1.0))

    def test_bad_counts_raise(self):
        with self.assertRaises(ValueError):
            wilson_interval(5, 3)


class MeasurementTests(unittest.TestCase):
    def test_construction_requires_coherent_interval(self):
        with self.assertRaises(ValueError):
            Measurement(
                label="x", kind="proportion", value=0.5, n=10,
                interval=(0.6, 0.9), method="wilson", confidence=0.95,
            )
        with self.assertRaises(ValueError):
            Measurement(
                label="x", kind="proportion", value=0.5, n=10,
                interval=(0.4, 0.6), method="", confidence=0.95,
            )

    def test_n_zero_renders_not_tested(self):
        m = proportion("untested", 0, 0)
        self.assertFalse(m.is_informative)
        self.assertIn("not tested", m.render())
        self.assertNotIn("0.0000 (", m.render())

    def test_render_always_includes_n(self):
        m = proportion("rate", 3, 40)
        self.assertIn("n=40", m.render())
        self.assertIn("wilson", m.render())


class DecideTests(unittest.TestCase):
    def test_pass_exception_inconclusive_lower_is_better(self):
        good = proportion("fp rate", 1, 1000, direction="lower_is_better")
        self.assertEqual(decide(good, 0.05).outcome, OUTCOME_PASS)
        bad = proportion("fp rate", 300, 1000, direction="lower_is_better")
        self.assertEqual(decide(bad, 0.05).outcome, OUTCOME_EXCEPTION)
        straddle = proportion("fp rate", 3, 60, direction="lower_is_better")
        self.assertEqual(decide(straddle, 0.05).outcome, OUTCOME_INCONCLUSIVE)

    def test_higher_is_better_mirrors(self):
        good = proportion("recall", 98, 100, direction="higher_is_better")
        self.assertEqual(decide(good, 0.9).outcome, OUTCOME_PASS)
        bad = proportion("recall", 10, 100, direction="higher_is_better")
        self.assertEqual(decide(bad, 0.9).outcome, OUTCOME_EXCEPTION)
        few = proportion("recall", 5, 5, direction="higher_is_better")
        self.assertEqual(decide(few, 0.9).outcome, OUTCOME_INCONCLUSIVE)

    def test_min_sample_gates_only_the_pass(self):
        small_clean = proportion("rate", 0, 5, direction="lower_is_better")
        self.assertEqual(decide(small_clean, 0.05).outcome, OUTCOME_INCONCLUSIVE)
        small_dirty = proportion("rate", 4, 5, direction="lower_is_better")
        self.assertEqual(decide(small_dirty, 0.05).outcome, OUTCOME_EXCEPTION)

    def test_zero_tolerance_attribute_rule(self):
        one_leak = proportion("leak", 1, 22, direction="lower_is_better")
        self.assertEqual(decide(one_leak, 0.0).outcome, OUTCOME_EXCEPTION)
        clean = proportion("leak", 0, 22, direction="lower_is_better")
        d = decide(clean, 0.0)
        self.assertEqual(d.outcome, OUTCOME_PASS)
        self.assertIn("interval", d.reason)
        tiny = proportion("leak", 0, 8, direction="lower_is_better")
        self.assertEqual(decide(tiny, 0.0).outcome, OUTCOME_INCONCLUSIVE)

    def test_neutral_direction_refuses(self):
        m = proportion("rate", 1, 10)
        with self.assertRaises(ValueError):
            decide(m, 0.5)

    def test_decision_serializes(self):
        m = proportion("rate", 1, 40, direction="lower_is_better")
        d = decide(m, 0.1)
        self.assertIsInstance(d, Decision)
        self.assertIn("measurement", d.to_dict())


class DistributionTests(unittest.TestCase):
    def test_binom_known_values(self):
        self.assertAlmostEqual(binom_pmf(2, 4, 0.5), 0.375, places=12)
        self.assertAlmostEqual(binom_cdf(1, 3, 0.5), 0.5, places=12)
        self.assertAlmostEqual(binom_cdf(59, 59, 0.05), 1.0, places=12)
        # (1 - 0.05)^59: probability of zero deviations in 59 draws at 5%
        self.assertAlmostEqual(binom_pmf(0, 59, 0.05), 0.95 ** 59, places=12)

    def test_binom_edges(self):
        self.assertEqual(binom_pmf(0, 10, 0.0), 1.0)
        self.assertEqual(binom_pmf(10, 10, 1.0), 1.0)
        self.assertEqual(binom_pmf(3, 2, 0.5), 0.0)

    def test_hypergeom_known_value(self):
        # C(4,1)*C(6,2)/C(10,3) = 4*15/120 = 0.5
        self.assertAlmostEqual(hypergeom_pmf(1, 10, 4, 3), 0.5, places=12)
        self.assertAlmostEqual(
            hypergeom_cdf(3, 10, 4, 3), 1.0, places=12
        )
        total = sum(hypergeom_pmf(k, 50, 10, 12) for k in range(0, 11))
        self.assertAlmostEqual(total, 1.0, places=12)

    def test_hypergeom_support_edges(self):
        self.assertEqual(hypergeom_pmf(5, 10, 4, 3), 0.0)
        with self.assertRaises(ValueError):
            hypergeom_pmf(1, 10, 11, 3)


class ChiSquareTests(unittest.TestCase):
    def test_critical_values(self):
        """Classic critical points recomputed from the incomplete gamma —
        agreement with published values is a test of the math, not a source
        of it (DECISIONS D-005)."""
        self.assertAlmostEqual(chi_square_sf(3.841459, 1), 0.05, places=5)
        self.assertAlmostEqual(chi_square_sf(15.50731, 8), 0.05, places=5)
        self.assertAlmostEqual(chi_square_sf(16.91898, 9), 0.05, places=5)
        self.assertAlmostEqual(chi_square_sf(20.09024, 8), 0.01, places=5)

    def test_edges(self):
        self.assertEqual(chi_square_sf(0.0, 5), 1.0)
        self.assertLess(chi_square_sf(1000.0, 2), 1e-12)
        with self.assertRaises(ValueError):
            chi_square_sf(-1.0, 2)
        with self.assertRaises(ValueError):
            chi_square_sf(1.0, 0)


if __name__ == "__main__":
    unittest.main()
