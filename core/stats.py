"""Statistics core: Measurement (uncertainty enforced at construction),
Wilson intervals, interval-based decisions, and first-principles
distributions (binomial, hypergeometric, chi-square survival).

Re-implements toolkit discipline, cited in DECISIONS.md:
- D-008 there / D-004 here: a proportion Measurement cannot exist without an
  interval, a named method, a confidence level, and n. n=0 renders as "not
  tested" with interval [0, 1] — never "0%".
- D-011 there: decisions compare the interval to the threshold, not the
  point estimate, and inconclusive is a real outcome. min_sample gates only
  the pass.
- D-012 there: zero-tolerance thresholds switch to the attribute rule (any
  exception is an exception; zero exceptions passes once n meets the
  minimum, with the interval reported alongside).

All distribution math is computed from the defining formulas (this repo's
D-005): exact integer combinatorics for binomial/hypergeometric mass, and
the standard series / continued-fraction evaluation of the regularized
incomplete gamma for the chi-square survival function.
"""

import math
from dataclasses import dataclass
from fractions import Fraction
from statistics import NormalDist

DEFAULT_CONFIDENCE = 0.95

OUTCOME_PASS = "pass"
OUTCOME_EXCEPTION = "exception"
OUTCOME_INCONCLUSIVE = "inconclusive"

DIRECTIONS = ("lower_is_better", "higher_is_better", "neutral")


def z_value(confidence: float) -> float:
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    return NormalDist().inv_cdf(0.5 + confidence / 2.0)


def wilson_interval(successes: int, n: int, confidence: float = DEFAULT_CONFIDENCE):
    """Wilson score interval for a binomial proportion.

    Chosen over the normal approximation because audit rates cluster at 0
    and 1, where the normal approximation reports zero width and implies
    certainty from a handful of observations (toolkit D-008). n=0 yields
    [0, 1]: "not tested", never "0%".
    """
    if n < 0 or successes < 0 or successes > n:
        raise ValueError(f"bad counts: {successes}/{n}")
    if n == 0:
        return (0.0, 1.0)
    z = z_value(confidence)
    p = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    lo = 0.0 if successes == 0 else max(0.0, center - half)
    hi = 1.0 if successes == n else min(1.0, center + half)
    return (lo, hi)


@dataclass(frozen=True)
class Measurement:
    """A rate that cannot be separated from its uncertainty.

    Construction raises unless the interval, method, confidence and n are
    all present and coherent; render() is the sanctioned display and always
    includes n.
    """

    label: str
    kind: str            # "proportion"
    value: float
    n: int
    interval: tuple
    method: str
    confidence: float
    direction: str = "neutral"
    numerator: int = None

    def __post_init__(self):
        if self.kind != "proportion":
            raise ValueError(f"unsupported measurement kind: {self.kind!r}")
        if self.direction not in DIRECTIONS:
            raise ValueError(f"unknown direction: {self.direction!r}")
        if self.n < 0:
            raise ValueError("n must be >= 0")
        if not self.method:
            raise ValueError("a measurement requires a named interval method")
        if not 0.0 < self.confidence < 1.0:
            raise ValueError("confidence must be in (0, 1)")
        if (
            not isinstance(self.interval, tuple)
            or len(self.interval) != 2
            or not all(isinstance(x, float) for x in self.interval)
        ):
            raise ValueError("interval must be a (lo, hi) float tuple")
        lo, hi = self.interval
        if not (0.0 <= lo <= hi <= 1.0):
            raise ValueError(f"malformed interval: {self.interval}")
        if self.n == 0:
            if self.interval != (0.0, 1.0):
                raise ValueError("n=0 must carry the uninformative interval (0, 1)")
        else:
            if not (0.0 <= self.value <= 1.0):
                raise ValueError("proportion value outside [0, 1]")
            eps = 1e-12
            if not (lo - eps <= self.value <= hi + eps):
                raise ValueError("value must lie inside its interval")

    @property
    def is_informative(self) -> bool:
        return self.n > 0

    def render(self) -> str:
        lo, hi = self.interval
        if self.n == 0:
            return f"not tested (n=0; interval {lo:.4f}-{hi:.4f})"
        pct = int(round(self.confidence * 100))
        return (
            f"{self.value:.4f} ({pct}% {self.method} {lo:.4f}-{hi:.4f}, n={self.n})"
        )

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "kind": self.kind,
            "value": round(self.value, 6),
            "n": self.n,
            "interval": [round(self.interval[0], 6), round(self.interval[1], 6)],
            "method": self.method,
            "confidence": self.confidence,
            "direction": self.direction,
            "numerator": self.numerator,
            "rendered": self.render(),
        }


def proportion(
    label: str,
    successes: int,
    n: int,
    confidence: float = DEFAULT_CONFIDENCE,
    direction: str = "neutral",
) -> Measurement:
    return Measurement(
        label=label,
        kind="proportion",
        value=(successes / n) if n else 0.0,
        n=n,
        interval=wilson_interval(successes, n, confidence),
        method="wilson",
        confidence=confidence,
        direction=direction,
        numerator=successes,
    )


@dataclass(frozen=True)
class Decision:
    outcome: str
    reason: str
    threshold: float
    min_sample: int
    measurement: Measurement

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "reason": self.reason,
            "threshold": self.threshold,
            "min_sample": self.min_sample,
            "measurement": self.measurement.to_dict(),
        }


def decide(measurement: Measurement, threshold: float, min_sample: int = 20) -> Decision:
    """Three outcomes, decided against the interval (toolkit D-011/D-012).

    Pass: the whole interval sits on the acceptable side (and n >= min_sample
    — only the reassuring conclusion must earn its sample size).
    Exception: the whole interval sits on the unacceptable side, or any
    exception under a zero-tolerance threshold.
    Inconclusive: the interval straddles, or a would-be pass lacks sample.
    """
    d = measurement.direction
    if d == "neutral":
        raise ValueError("cannot decide a neutral-direction measurement")
    lo, hi = measurement.interval
    n = measurement.n

    def mk(outcome, reason):
        return Decision(outcome, reason, threshold, min_sample, measurement)

    if n == 0:
        return mk(OUTCOME_INCONCLUSIVE, "not tested (n=0)")

    if d == "lower_is_better" and threshold == 0.0:
        # Zero tolerance: attribute rule.
        if measurement.value > 0:
            return mk(
                OUTCOME_EXCEPTION,
                "exceptions observed under a zero-tolerance criterion",
            )
        if n >= min_sample:
            return mk(
                OUTCOME_PASS,
                f"no exceptions in n={n}; the interval is reported alongside "
                f"so the reader can see what that sample size buys",
            )
        return mk(
            OUTCOME_INCONCLUSIVE,
            f"no exceptions, but n={n} is below min_sample={min_sample}",
        )

    if d == "lower_is_better":
        if hi <= threshold:
            if n >= min_sample:
                return mk(OUTCOME_PASS, "entire interval at or below threshold")
            return mk(
                OUTCOME_INCONCLUSIVE,
                f"interval below threshold but n={n} < min_sample={min_sample}",
            )
        if lo > threshold:
            return mk(OUTCOME_EXCEPTION, "entire interval above threshold")
        return mk(OUTCOME_INCONCLUSIVE, "interval straddles the threshold")

    # higher_is_better
    if lo >= threshold:
        if n >= min_sample:
            return mk(OUTCOME_PASS, "entire interval at or above threshold")
        return mk(
            OUTCOME_INCONCLUSIVE,
            f"interval above threshold but n={n} < min_sample={min_sample}",
        )
    if hi < threshold:
        return mk(OUTCOME_EXCEPTION, "entire interval below threshold")
    return mk(OUTCOME_INCONCLUSIVE, "interval straddles the threshold")


# --- exact distributions (D-005: formulas, not tables) ----------------------


def binom_pmf(k: int, n: int, p: float) -> float:
    if not 0 <= k <= n:
        return 0.0
    if not 0.0 <= p <= 1.0:
        raise ValueError("p must be in [0, 1]")
    if p == 0.0:
        return 1.0 if k == 0 else 0.0
    if p == 1.0:
        return 1.0 if k == n else 0.0
    log_pmf = (
        math.lgamma(n + 1)
        - math.lgamma(k + 1)
        - math.lgamma(n - k + 1)
        + k * math.log(p)
        + (n - k) * math.log1p(-p)
    )
    return math.exp(log_pmf)


def binom_cdf(k: int, n: int, p: float) -> float:
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return min(1.0, math.fsum(binom_pmf(i, n, p) for i in range(0, k + 1)))


def hypergeom_pmf(k: int, population: int, successes: int, draws: int) -> float:
    """P(X = k) drawing `draws` without replacement from `population` items
    of which `successes` are marked. Exact integer combinatorics."""
    if population < 0 or not 0 <= successes <= population or not 0 <= draws <= population:
        raise ValueError("bad hypergeometric parameters")
    if k < max(0, draws - (population - successes)) or k > min(draws, successes):
        return 0.0
    num = math.comb(successes, k) * math.comb(population - successes, draws - k)
    den = math.comb(population, draws)
    return float(Fraction(num, den))


def hypergeom_cdf(k: int, population: int, successes: int, draws: int) -> float:
    lo = max(0, draws - (population - successes))
    if k < lo:
        return 0.0
    hi = min(draws, successes)
    if k >= hi:
        return 1.0
    total = Fraction(0)
    den = math.comb(population, draws)
    for i in range(lo, k + 1):
        total += Fraction(
            math.comb(successes, i) * math.comb(population - successes, draws - i),
            den,
        )
    return float(total)


# --- chi-square survival via regularized incomplete gamma -------------------


def _gamma_p_series(a: float, x: float, eps: float = 1e-14, max_iter: int = 1000) -> float:
    ap = a
    total = 1.0 / a
    delta = total
    for _ in range(max_iter):
        ap += 1.0
        delta *= x / ap
        total += delta
        if abs(delta) < abs(total) * eps:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gamma_q_contfrac(a: float, x: float, eps: float = 1e-14, max_iter: int = 1000) -> float:
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b if b != 0.0 else 1.0 / tiny
    h = d
    for i in range(1, max_iter + 1):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def regularized_gamma_q(a: float, x: float) -> float:
    """Q(a, x) = Γ(a, x)/Γ(a), the upper regularized incomplete gamma."""
    if a <= 0.0 or x < 0.0:
        raise ValueError("require a > 0 and x >= 0")
    if x == 0.0:
        return 1.0
    if x < a + 1.0:
        return max(0.0, min(1.0, 1.0 - _gamma_p_series(a, x)))
    return max(0.0, min(1.0, _gamma_q_contfrac(a, x)))


def chi_square_sf(x: float, df: int) -> float:
    """P(X >= x) for a chi-square with df degrees of freedom."""
    if df <= 0:
        raise ValueError("df must be positive")
    if x < 0:
        raise ValueError("x must be non-negative")
    return regularized_gamma_q(df / 2.0, x / 2.0)
