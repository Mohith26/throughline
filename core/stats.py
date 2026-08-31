"""Statistics for verification planning and reliability claims.

Everything is implemented from the definitions with no third party library, for
two reasons. The obvious one is that the tool then has no dependencies. The one
that actually matters is that a reliability claim in a design history file has to
be defensible line by line, and "the library said so" is not a defence. Each
function below states which definition it implements, and the tests check the
values against published tables rather than against a previous run of this code.

The numerical core is the regularised incomplete beta function, because the
binomial cumulative distribution and the Clopper-Pearson interval are both
expressed through it.
"""

import math

MAX_ITER = 300
EPS = 3.0e-16
TINY = 1.0e-300


def log_beta(a, b):
    return math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)


def _betacf(a, b, x):
    """Continued fraction for the incomplete beta, modified Lentz method."""
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < TINY:
        d = TINY
    d = 1.0 / d
    h = d
    for m in range(1, MAX_ITER + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < TINY:
            d = TINY
        c = 1.0 + aa / c
        if abs(c) < TINY:
            c = TINY
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < TINY:
            d = TINY
        c = 1.0 + aa / c
        if abs(c) < TINY:
            c = TINY
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            return h
    raise ArithmeticError("incomplete beta did not converge for a=%g b=%g x=%g" % (a, b, x))


def betainc(a, b, x):
    """Regularised incomplete beta I_x(a, b)."""
    if x < 0.0 or x > 1.0:
        raise ValueError("x must lie in [0, 1], got %r" % x)
    if x == 0.0:
        return 0.0
    if x == 1.0:
        return 1.0
    front = math.exp(a * math.log(x) + b * math.log(1.0 - x) - log_beta(a, b))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def binomial_cdf(k, n, p):
    """P(X <= k) for X ~ Binomial(n, p), via the incomplete beta identity."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    if p <= 0.0:
        return 1.0
    if p >= 1.0:
        return 0.0
    return betainc(n - k, k + 1, 1.0 - p)


def clopper_pearson(failures, n, confidence=0.95):
    """Exact two sided interval for a proportion.

    Returns (low, high) for the failure proportion. Exact means it is built from
    the binomial distribution directly rather than a normal approximation, so it
    never produces a bound outside [0, 1] and it stays honest at the small sample
    sizes design verification actually uses.
    """
    if not 0 <= failures <= n:
        raise ValueError("failures must lie in [0, n]")
    if n == 0:
        return 0.0, 1.0
    alpha = 1.0 - confidence
    tail = alpha / 2.0
    low = 0.0 if failures == 0 else _solve_low(failures, n, tail)
    high = 1.0 if failures == n else _solve_high(failures, n, tail)
    return low, high


def _solve_low(failures, n, tail):
    # Lower bound solves P(X >= failures | p) = tail.
    def f(p):
        return 1.0 - binomial_cdf(failures - 1, n, p)
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if f(mid) < tail:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _solve_high(failures, n, tail):
    # Upper bound solves P(X <= failures | p) = tail.
    def f(p):
        return binomial_cdf(failures, n, p)
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if f(mid) > tail:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def reliability_lower_bound(failures, n, confidence=0.95):
    """Lower confidence bound on reliability, which is 1 minus the upper bound on
    the failure proportion. This is the number a verification report should quote:
    "at least R reliability with C confidence"."""
    _, high = clopper_pearson(failures, n, confidence)
    return 1.0 - high


def zero_failure_sample_size(reliability, confidence=0.95):
    """Smallest n with zero failures that demonstrates the given reliability.

    From (reliability)^n <= 1 - confidence, the success run theorem. The classic
    result is that 90 percent reliability at 95 percent confidence needs 29 units,
    and 95/95 needs 59.
    """
    if not 0.0 < reliability < 1.0:
        raise ValueError("reliability must lie in (0, 1)")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must lie in (0, 1)")
    return int(math.ceil(math.log(1.0 - confidence) / math.log(reliability)))


def demonstrated_reliability(n, confidence=0.95):
    """The inverse of the above: what a clean run of n units actually proves."""
    if n <= 0:
        raise ValueError("n must be positive")
    return (1.0 - confidence) ** (1.0 / n)


# ---- Weibull ------------------------------------------------------------

def median_ranks(n):
    """Bernard's approximation, (i - 0.3) / (n + 0.4).

    The exact median rank is the median of the ith order statistic of a uniform
    sample, which needs an incomplete beta inversion per point. Bernard's
    approximation is what reliability practice uses and is within about 0.1
    percent over the range that matters.
    """
    return [(i - 0.3) / (n + 0.4) for i in range(1, n + 1)]


def weibull_fit(times):
    """Two parameter Weibull by median rank regression.

    Returns (shape, scale, r_squared). The regression is of ln(-ln(1 - F)) on
    ln(t), where the slope is the shape parameter and the intercept gives the
    scale. Median rank regression rather than maximum likelihood because it is
    the method reliability standards describe, it is stable at the sample sizes
    used in design verification, and it produces the r squared that tells you
    whether a Weibull was the right model at all.
    """
    data = sorted(float(t) for t in times)
    if len(data) < 3:
        raise ValueError("need at least three failure times to fit")
    if data[0] <= 0:
        raise ValueError("failure times must be positive")

    ranks = median_ranks(len(data))
    xs = [math.log(t) for t in data]
    ys = [math.log(-math.log(1.0 - f)) for f in ranks]

    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    if sxx == 0:
        raise ValueError("all failure times are identical, cannot fit")
    slope = sxy / sxx
    intercept = my - slope * mx

    shape = slope
    scale = math.exp(-intercept / slope)

    syy = sum((y - my) ** 2 for y in ys)
    r_squared = (sxy * sxy) / (sxx * syy) if syy > 0 else 1.0
    return shape, scale, r_squared


def weibull_reliability(t, shape, scale):
    if t < 0:
        raise ValueError("t must be non negative")
    return math.exp(-((t / scale) ** shape))


def weibull_bx_life(fraction, shape, scale):
    """The B(x) life: the time by which the given fraction has failed. B10 is the
    number quoted in most device reliability requirements."""
    if not 0.0 < fraction < 1.0:
        raise ValueError("fraction must lie in (0, 1)")
    return scale * (-math.log(1.0 - fraction)) ** (1.0 / shape)


def interpret_shape(shape):
    """What the shape parameter says about the failure mode. This is the sentence
    a reliability engineer writes underneath the plot, and getting it backwards is
    a common and expensive mistake."""
    if shape < 0.95:
        return "decreasing hazard, consistent with infant mortality"
    if shape <= 1.05:
        return "constant hazard, consistent with random failures"
    return "increasing hazard, consistent with wear out"
