"""Statistics tests, checked against published values rather than against a
previous run of this code.

Where a number is quoted from a table or a closed form, the source of the number
is named in the test, because "it matches what it produced last time" is not
evidence that a reliability claim is correct.
"""

import math
import unittest

from core import stats


class IncompleteBetaTests(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(stats.betainc(2, 3, 0.0), 0.0)
        self.assertEqual(stats.betainc(2, 3, 1.0), 1.0)

    def test_symmetry_identity(self):
        # I_x(a,b) = 1 - I_(1-x)(b,a), which holds for the exact function and is
        # a genuine check on both branches of the continued fraction.
        for a, b, x in [(2, 3, 0.4), (0.5, 0.5, 0.7), (10, 1, 0.9), (1, 10, 0.1),
                        (7.5, 2.5, 0.33)]:
            left = stats.betainc(a, b, x)
            right = 1.0 - stats.betainc(b, a, 1.0 - x)
            self.assertAlmostEqual(left, right, places=12, msg="a=%s b=%s x=%s" % (a, b, x))

    def test_uniform_case(self):
        # I_x(1,1) is just x.
        for x in [0.1, 0.25, 0.5, 0.75, 0.9]:
            self.assertAlmostEqual(stats.betainc(1, 1, x), x, places=12)

    def test_known_value(self):
        # I_0.5(2,2) = 0.5 by symmetry of the Beta(2,2) density about 0.5.
        self.assertAlmostEqual(stats.betainc(2, 2, 0.5), 0.5, places=12)
        # I_0.5(1,2) = 1 - (1-0.5)^2 = 0.75.
        self.assertAlmostEqual(stats.betainc(1, 2, 0.5), 0.75, places=12)

    def test_out_of_range_is_rejected(self):
        with self.assertRaises(ValueError):
            stats.betainc(2, 2, 1.5)


class BinomialTests(unittest.TestCase):
    def _brute(self, k, n, p):
        total = 0.0
        for i in range(0, k + 1):
            total += math.comb(n, i) * (p ** i) * ((1 - p) ** (n - i))
        return total

    def test_matches_direct_summation(self):
        for n in [1, 5, 12, 30]:
            for p in [0.05, 0.2, 0.5, 0.83]:
                for k in range(0, n + 1):
                    self.assertAlmostEqual(
                        stats.binomial_cdf(k, n, p), self._brute(k, n, p), places=11,
                        msg="k=%d n=%d p=%s" % (k, n, p))

    def test_edges(self):
        self.assertEqual(stats.binomial_cdf(-1, 10, 0.3), 0.0)
        self.assertEqual(stats.binomial_cdf(10, 10, 0.3), 1.0)
        self.assertEqual(stats.binomial_cdf(3, 10, 0.0), 1.0)
        self.assertEqual(stats.binomial_cdf(3, 10, 1.0), 0.0)


class ClopperPearsonTests(unittest.TestCase):
    def test_zero_failures_lower_bound_is_zero(self):
        low, high = stats.clopper_pearson(0, 29, 0.95)
        self.assertEqual(low, 0.0)
        # Published value: with 0 failures in 29, the 95 percent upper bound on
        # the failure rate is 0.0982, so reliability is 0.9018.
        self.assertAlmostEqual(high, 0.09823, places=4)

    def test_all_failures_upper_bound_is_one(self):
        low, high = stats.clopper_pearson(5, 5, 0.95)
        self.assertEqual(high, 1.0)
        self.assertGreater(low, 0.4)

    def test_known_interval(self):
        # A textbook case: 2 failures in 20 at 95 percent gives roughly
        # (0.0123, 0.3170).
        low, high = stats.clopper_pearson(2, 20, 0.95)
        self.assertAlmostEqual(low, 0.01235, places=4)
        self.assertAlmostEqual(high, 0.31698, places=4)

    def test_interval_contains_the_point_estimate(self):
        for failures, n in [(1, 10), (3, 30), (7, 50), (12, 100)]:
            low, high = stats.clopper_pearson(failures, n, 0.95)
            self.assertLessEqual(low, failures / float(n))
            self.assertLessEqual(failures / float(n), high)

    def test_interval_narrows_as_n_grows(self):
        widths = []
        for n in [10, 50, 200, 1000]:
            low, high = stats.clopper_pearson(int(0.1 * n), n, 0.95)
            widths.append(high - low)
        for i in range(1, len(widths)):
            self.assertLess(widths[i], widths[i - 1])

    def test_higher_confidence_gives_a_wider_interval(self):
        narrow = stats.clopper_pearson(3, 40, 0.90)
        wide = stats.clopper_pearson(3, 40, 0.99)
        self.assertLess(narrow[0] - wide[0], 1e-9 + (narrow[0] - wide[0]))
        self.assertGreater(wide[1], narrow[1])
        self.assertLess(wide[0], narrow[0])

    def test_bounds_stay_inside_zero_and_one(self):
        for failures, n in [(0, 1), (1, 1), (0, 3), (3, 3)]:
            low, high = stats.clopper_pearson(failures, n, 0.95)
            self.assertGreaterEqual(low, 0.0)
            self.assertLessEqual(high, 1.0)

    def test_invalid_input(self):
        with self.assertRaises(ValueError):
            stats.clopper_pearson(5, 3, 0.95)


class SuccessRunTests(unittest.TestCase):
    def test_classic_sample_sizes(self):
        # The two numbers every reliability plan quotes.
        self.assertEqual(stats.zero_failure_sample_size(0.90, 0.95), 29)
        self.assertEqual(stats.zero_failure_sample_size(0.95, 0.95), 59)
        self.assertEqual(stats.zero_failure_sample_size(0.99, 0.95), 299)
        self.assertEqual(stats.zero_failure_sample_size(0.90, 0.90), 22)

    def test_round_trip_against_demonstrated_reliability(self):
        for reliability in [0.80, 0.90, 0.95, 0.99]:
            n = stats.zero_failure_sample_size(reliability, 0.95)
            shown = stats.demonstrated_reliability(n, 0.95)
            self.assertGreaterEqual(shown, reliability)
            # One unit fewer must not be enough, which is what makes it minimal.
            self.assertLess(stats.demonstrated_reliability(n - 1, 0.95), reliability)

    def test_agrees_with_the_exact_binomial_bound(self):
        # The success run formula should match the Clopper-Pearson reliability
        # bound for a clean run. Two independent routes to the same number.
        for n in [12, 29, 59]:
            formula = stats.demonstrated_reliability(n, 0.95)
            exact = stats.reliability_lower_bound(0, n, 0.95)
            self.assertAlmostEqual(formula, exact, places=6)

    def test_invalid_input(self):
        with self.assertRaises(ValueError):
            stats.zero_failure_sample_size(1.0, 0.95)
        with self.assertRaises(ValueError):
            stats.demonstrated_reliability(0)


class WeibullTests(unittest.TestCase):
    def test_median_ranks_are_increasing_and_bounded(self):
        ranks = stats.median_ranks(10)
        self.assertEqual(len(ranks), 10)
        for i in range(1, len(ranks)):
            self.assertGreater(ranks[i], ranks[i - 1])
        self.assertGreater(ranks[0], 0.0)
        self.assertLess(ranks[-1], 1.0)

    def test_median_rank_known_value(self):
        # Bernard: (1 - 0.3) / (5 + 0.4) = 0.12963
        self.assertAlmostEqual(stats.median_ranks(5)[0], 0.129630, places=6)

    def test_fit_recovers_known_parameters(self):
        # Generate exact quantiles of a Weibull(shape=2.0, scale=1000) at the
        # median rank positions. A correct fit has to return the parameters it
        # was built from, to within regression error.
        shape, scale = 2.0, 1000.0
        n = 30
        times = [scale * (-math.log(1.0 - f)) ** (1.0 / shape)
                 for f in stats.median_ranks(n)]
        fit_shape, fit_scale, r2 = stats.weibull_fit(times)
        self.assertAlmostEqual(fit_shape, shape, places=6)
        self.assertAlmostEqual(fit_scale, scale, places=4)
        self.assertGreater(r2, 0.9999)

    def test_fit_recovers_a_different_shape(self):
        shape, scale = 0.7, 250.0
        times = [scale * (-math.log(1.0 - f)) ** (1.0 / shape)
                 for f in stats.median_ranks(25)]
        fit_shape, fit_scale, _ = stats.weibull_fit(times)
        self.assertAlmostEqual(fit_shape, shape, places=6)
        self.assertAlmostEqual(fit_scale, scale, places=4)

    def test_reliability_at_the_scale_is_one_over_e(self):
        # By definition R(eta) = exp(-1) for any shape.
        for shape in [0.5, 1.0, 2.0, 4.0]:
            self.assertAlmostEqual(stats.weibull_reliability(1000.0, shape, 1000.0),
                                   math.exp(-1.0), places=12)

    def test_bx_life_inverts_reliability(self):
        shape, scale = 2.2, 1450.0
        for fraction in [0.01, 0.1, 0.5]:
            t = stats.weibull_bx_life(fraction, shape, scale)
            self.assertAlmostEqual(stats.weibull_reliability(t, shape, scale),
                                   1.0 - fraction, places=12)

    def test_b10_is_shorter_than_b50(self):
        shape, scale = 2.2, 1450.0
        self.assertLess(stats.weibull_bx_life(0.10, shape, scale),
                        stats.weibull_bx_life(0.50, shape, scale))

    def test_shape_interpretation(self):
        self.assertIn("infant", stats.interpret_shape(0.6))
        self.assertIn("random", stats.interpret_shape(1.0))
        self.assertIn("wear out", stats.interpret_shape(3.0))

    def test_too_few_points_is_rejected(self):
        with self.assertRaises(ValueError):
            stats.weibull_fit([100.0, 200.0])

    def test_non_positive_times_are_rejected(self):
        with self.assertRaises(ValueError):
            stats.weibull_fit([0.0, 100.0, 200.0])

    def test_identical_times_are_rejected(self):
        with self.assertRaises(ValueError):
            stats.weibull_fit([100.0, 100.0, 100.0])


if __name__ == "__main__":
    unittest.main()
