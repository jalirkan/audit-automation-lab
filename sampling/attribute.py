"""Attribute-sampling mathematics, from the defining distributions.

Sample size: the smallest n whose planned deviation allowance c (expected
deviations rounded up) still leaves at most `risk` probability of observing
<= c deviations when the true rate equals the tolerable rate:

    P(X <= c | rate = tolerable) <= risk,  c = ceil(expected_rate * n)

Upper deviation limit: the exact one-sided upper bound — the smallest rate
that would leave at most `risk` probability of seeing as few deviations as
the sample actually produced:

    UDL = min { p : P(X <= observed | rate = p) <= risk }

Both come in binomial (large population) and hypergeometric (finite
population, deviations counted in whole items) forms, computed with the
exact mass functions in core.stats. Where these results agree with the
classic AICPA-style tables (n=59 at 5%/5%/0 expected, n=22 at 10%/10%/0),
that agreement is a *test of the math, not a source of it* (DECISIONS
D-005): the tests recompute the anchors from the formulas.

Reference: AU-C 530 (original one-line summary in rules.base.REFERENCES).

Bridge to full-population analytics (used verbatim by the workpapers):
BRIDGE_NOTE below. The analytics examine 100% of the population and
stratify it into flagged and unflagged; sampling math answers a different
question — what a manual review of a random sample drawn from a stratum
supports about that stratum, at a stated risk. It never converts a
full-population screen into a statistical sample after the fact.
"""

import math
from dataclasses import dataclass

from core.stats import binom_cdf, hypergeom_cdf

BRIDGE_NOTE = (
    "The rule battery is a complete examination that stratifies the "
    "population into flagged and unflagged entries; it is not a sample and "
    "supports no projection beyond itself. Where the audit response to a "
    "flagged stratum is manual review of a random sample drawn from that "
    "stratum, the attribute-sampling mathematics here quantifies what that "
    "sample supports about the stratum at a stated risk of overreliance — "
    "and nothing more."
)

OUTCOME_SUPPORTS = "pass"
OUTCOME_EXCEPTION = "exception"
OUTCOME_INCONCLUSIVE = "inconclusive"


def _validate_common(tolerable_rate, risk):
    if not 0.0 < tolerable_rate < 1.0:
        raise ValueError("tolerable_rate must be in (0, 1)")
    if not 0.0 < risk < 1.0:
        raise ValueError("risk must be in (0, 1)")


@dataclass(frozen=True)
class SampleSize:
    n: int
    allowance: int          # planned deviation allowance c
    achieved_risk: float    # P(X <= c | tolerable) at the chosen n
    method: str             # "binomial" | "hypergeometric"
    tolerable_rate: float
    expected_rate: float
    risk: float
    population: int         # None for binomial

    def to_dict(self) -> dict:
        return {
            "n": self.n,
            "allowance": self.allowance,
            "achieved_risk": round(self.achieved_risk, 6),
            "method": self.method,
            "tolerable_rate": self.tolerable_rate,
            "expected_rate": self.expected_rate,
            "risk": self.risk,
            "population": self.population,
        }


def attribute_sample_size(
    tolerable_rate: float,
    risk: float,
    expected_rate: float = 0.0,
    population: int = None,
    max_n: int = 20_000,
) -> SampleSize:
    """Smallest n meeting the planning condition; raises if none exists
    (expected rate at or above tolerable, or a finite population too small
    to discriminate)."""
    _validate_common(tolerable_rate, risk)
    if not 0.0 <= expected_rate < tolerable_rate:
        raise ValueError(
            "expected_rate must be below tolerable_rate; a sample cannot "
            "support reliance when deviations are expected at the tolerable "
            "rate itself"
        )
    if population is not None:
        if population <= 0:
            raise ValueError("population must be positive")
        k_pop = math.ceil(tolerable_rate * population)
        limit = population
    else:
        limit = max_n

    n = 1
    while n <= limit:
        c = math.ceil(expected_rate * n)
        if c < n:  # a sample all of whose items may deviate decides nothing
            if population is None:
                p = binom_cdf(c, n, tolerable_rate)
            else:
                draws_possible = min(n, population)
                p = hypergeom_cdf(c, population, k_pop, draws_possible)
            if p <= risk:
                return SampleSize(
                    n=n,
                    allowance=c,
                    achieved_risk=p,
                    method="binomial" if population is None else "hypergeometric",
                    tolerable_rate=tolerable_rate,
                    expected_rate=expected_rate,
                    risk=risk,
                    population=population,
                )
        n += 1
    raise ValueError(
        f"no sample size up to {limit} satisfies tolerable={tolerable_rate}, "
        f"expected={expected_rate}, risk={risk}"
        + ("" if population is None else f", population={population}")
    )


@dataclass(frozen=True)
class UpperDeviationLimit:
    n: int
    deviations: int
    sample_rate: float
    udl: float
    confidence: float       # 1 - risk, one-sided
    method: str
    population: int         # None for binomial
    population_deviations_bound: int  # smallest K for hypergeometric; None otherwise

    def to_dict(self) -> dict:
        return {
            "n": self.n,
            "deviations": self.deviations,
            "sample_rate": round(self.sample_rate, 6),
            "udl": round(self.udl, 6),
            "confidence": self.confidence,
            "method": self.method,
            "population": self.population,
            "population_deviations_bound": self.population_deviations_bound,
            "statement": (
                f"at {self.confidence:.0%} one-sided confidence, the "
                f"deviation rate does not exceed {self.udl:.4f} "
                f"(sample: {self.deviations}/{self.n}, n={self.n})"
            ),
        }


def upper_deviation_limit(
    n: int,
    deviations: int,
    risk: float,
    population: int = None,
) -> UpperDeviationLimit:
    """Exact one-sided upper bound on the deviation rate."""
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0 <= deviations <= n:
        raise ValueError("deviations must be within 0..n")
    if not 0.0 < risk < 1.0:
        raise ValueError("risk must be in (0, 1)")

    if population is None:
        if deviations == n:
            udl = 1.0
        else:
            lo, hi = deviations / n, 1.0
            for _ in range(200):  # fixed iteration count: deterministic
                mid = (lo + hi) / 2.0
                if binom_cdf(deviations, n, mid) <= risk:
                    hi = mid
                else:
                    lo = mid
            udl = hi
        return UpperDeviationLimit(
            n=n,
            deviations=deviations,
            sample_rate=deviations / n,
            udl=udl,
            confidence=1.0 - risk,
            method="binomial",
            population=None,
            population_deviations_bound=None,
        )

    if population < n:
        raise ValueError("population must be at least n")
    k_bound = None
    for k_pop in range(deviations, population - n + deviations + 1):
        if hypergeom_cdf(deviations, population, k_pop, n) <= risk:
            k_bound = k_pop
            break
    if k_bound is None:
        k_bound = population - n + deviations  # every unseen item deviating
    return UpperDeviationLimit(
        n=n,
        deviations=deviations,
        sample_rate=deviations / n,
        udl=k_bound / population,
        confidence=1.0 - risk,
        method="hypergeometric",
        population=population,
        population_deviations_bound=k_bound,
    )


@dataclass(frozen=True)
class AttributeEvaluation:
    outcome: str
    reason: str
    tolerable_rate: float
    limit: UpperDeviationLimit

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "reason": self.reason,
            "tolerable_rate": self.tolerable_rate,
            "limit": self.limit.to_dict(),
        }


def evaluate_attribute_sample(
    n: int,
    deviations: int,
    tolerable_rate: float,
    risk: float,
    population: int = None,
) -> AttributeEvaluation:
    """Three outcomes, mirroring the interval logic of core.stats.decide:

    pass — the upper deviation limit is at or below tolerable: the sample
    supports reliance at this risk level.
    exception — the observed sample rate itself reaches tolerable: the
    control is failing on the sample's face.
    inconclusive — observed rate below tolerable but UDL above it: this
    sample size cannot answer the question at this risk.
    """
    _validate_common(tolerable_rate, risk)
    limit = upper_deviation_limit(n, deviations, risk, population=population)
    if limit.udl <= tolerable_rate:
        outcome = OUTCOME_SUPPORTS
        reason = (
            f"UDL {limit.udl:.4f} <= tolerable {tolerable_rate:.4f}: the "
            f"sample (n={n}) supports reliance at {1 - risk:.0%} one-sided "
            f"confidence"
        )
    elif limit.sample_rate >= tolerable_rate:
        outcome = OUTCOME_EXCEPTION
        reason = (
            f"observed rate {limit.sample_rate:.4f} at or above tolerable "
            f"{tolerable_rate:.4f}"
        )
    else:
        outcome = OUTCOME_INCONCLUSIVE
        reason = (
            f"observed rate {limit.sample_rate:.4f} below tolerable "
            f"{tolerable_rate:.4f}, but UDL {limit.udl:.4f} exceeds it: "
            f"n={n} cannot support reliance at this risk"
        )
    return AttributeEvaluation(
        outcome=outcome,
        reason=reason,
        tolerable_rate=tolerable_rate,
        limit=limit,
    )
