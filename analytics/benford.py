"""Benford first- and second-digit conformity tests.

Expected digit frequencies are computed from Benford's law directly:
P(first digit d) = log10(1 + 1/d); the second-digit distribution sums the
two-digit law over leading digits. Test statistics: Pearson chi-square with
its survival-function p-value (computed in core.stats from the incomplete
gamma), and MAD (mean absolute deviation of observed vs expected digit
proportions).

Provenance of thresholds: the MAD conformity bands are the ranges published
by Nigrini (2012), "Benford's Law" — cited as research constants, with the
band boundaries restated here as numbers, not as reproduced text. The
*decision* rests on MAD, not the p-value, and the reason is printed with
every result: chi-square power grows with n, so at ledger scale it rejects
for deviations far too small to matter, while MAD measures the size of the
deviation itself.

Applicability guard (DECISIONS D-015): the test refuses — returning an
inconclusive, p-value-free result — when its assumptions fail: too few
values, too narrow a span of magnitudes (Benford needs data crossing
orders of magnitude), or a population dominated by repeated identical
amounts (assigned or contractual numbers, which no digit law describes).
"""

import math
from dataclasses import dataclass

from core.stats import DEFAULT_CONFIDENCE, chi_square_sf, proportion

FIRST_DIGITS = tuple(range(1, 10))
SECOND_DIGITS = tuple(range(0, 10))

# MAD conformity bands (Nigrini 2012): (close, acceptable, marginal) upper
# bounds; above the last is nonconformity.
MAD_BANDS_FIRST = (0.006, 0.012, 0.015)
MAD_BANDS_SECOND = (0.008, 0.010, 0.012)
BAND_NAMES = ("close conformity", "acceptable conformity", "marginal conformity")

CONCLUSION_CONFORMING = "conforming"
CONCLUSION_NONCONFORMING = "nonconforming"
CONCLUSION_INCONCLUSIVE = "inconclusive"


def benford_first_expected() -> dict:
    return {d: math.log10(1.0 + 1.0 / d) for d in FIRST_DIGITS}


def benford_second_expected() -> dict:
    out = {}
    for d in SECOND_DIGITS:
        out[d] = sum(
            math.log10(1.0 + 1.0 / (10 * lead + d)) for lead in range(1, 10)
        )
    return out


def first_digit(amount_cents: int) -> int:
    if amount_cents <= 0:
        raise ValueError("digit tests need positive amounts")
    s = str(amount_cents)
    return int(s[0])


def second_digit(amount_cents: int):
    """Second significant digit, or None for single-digit values."""
    if amount_cents <= 0:
        raise ValueError("digit tests need positive amounts")
    s = str(amount_cents)
    return int(s[1]) if len(s) > 1 else None


@dataclass(frozen=True)
class BenfordResult:
    test: str                 # "first_digit" | "second_digit"
    applicable: bool
    refusal_reason: str
    n: int
    counts: dict              # digit -> observed count
    expected_proportions: dict
    digit_measurements: dict  # digit -> Measurement (Wilson, always with n)
    chi_square: float
    chi_square_df: int
    p_value: float            # None when not applicable
    mad: float
    mad_band: str
    conclusion: str
    conclusion_reason: str

    def to_dict(self) -> dict:
        return {
            "test": self.test,
            "applicable": self.applicable,
            "refusal_reason": self.refusal_reason,
            "n": self.n,
            "counts": {str(k): v for k, v in sorted(self.counts.items())},
            "expected_proportions": {
                str(k): round(v, 6) for k, v in sorted(self.expected_proportions.items())
            },
            "digit_measurements": {
                str(k): m.to_dict() for k, m in sorted(self.digit_measurements.items())
            },
            "chi_square": None if self.chi_square is None else round(self.chi_square, 4),
            "chi_square_df": self.chi_square_df,
            "p_value": None if self.p_value is None else round(self.p_value, 6),
            "mad": None if self.mad is None else round(self.mad, 6),
            "mad_band": self.mad_band,
            "conclusion": self.conclusion,
            "conclusion_reason": self.conclusion_reason,
        }


def _refuse(test, reason, n) -> BenfordResult:
    return BenfordResult(
        test=test,
        applicable=False,
        refusal_reason=reason,
        n=n,
        counts={},
        expected_proportions={},
        digit_measurements={},
        chi_square=None,
        chi_square_df=0,
        p_value=None,
        mad=None,
        mad_band="",
        conclusion=CONCLUSION_INCONCLUSIVE,
        conclusion_reason=(
            "test preconditions failed; emitting a p-value anyway would "
            "manufacture false precision — " + reason
        ),
    )


def _guard(amounts, min_n, span_min, max_mode_share, test):
    n = len(amounts)
    if n < min_n:
        return _refuse(
            test, f"only {n} usable amounts; minimum is {min_n}", n
        )
    lo, hi = min(amounts), max(amounts)
    if lo <= 0:
        return _refuse(test, "non-positive amounts present after filtering", n)
    span = hi / lo
    if span < span_min:
        return _refuse(
            test,
            f"amounts span a factor of {span:.1f}; Benford requires data "
            f"crossing orders of magnitude (minimum factor {span_min:.0f})",
            n,
        )
    counts = {}
    for a in amounts:
        counts[a] = counts.get(a, 0) + 1
    mode_value, mode_count = max(sorted(counts.items()), key=lambda kv: kv[1])
    if mode_count / n > max_mode_share:
        return _refuse(
            test,
            f"amount {mode_value} repeats in {mode_count}/{n} values "
            f"({mode_count / n:.1%}): population resembles assigned or "
            f"contractual amounts, which no digit law describes",
            n,
        )
    return None


def _band(mad, bands):
    for bound, name in zip(bands, BAND_NAMES):
        if mad <= bound:
            return name
    return "nonconformity"


def _run(test, digits_iter, expected, bands, confidence):
    observed = {d: 0 for d in expected}
    n = 0
    for d in digits_iter:
        observed[d] += 1
        n += 1
    chi = 0.0
    mad_total = 0.0
    measurements = {}
    for d in sorted(expected):
        exp_p = expected[d]
        exp_count = exp_p * n
        obs = observed[d]
        chi += (obs - exp_count) ** 2 / exp_count
        obs_p = obs / n
        mad_total += abs(obs_p - exp_p)
        measurements[d] = proportion(
            f"{test} = {d}", obs, n, confidence=confidence, direction="neutral"
        )
    mad = mad_total / len(expected)
    df = len(expected) - 1
    p = chi_square_sf(chi, df)
    band = _band(mad, bands)
    if band in (BAND_NAMES[0], BAND_NAMES[1]):
        conclusion = CONCLUSION_CONFORMING
    elif band == BAND_NAMES[2]:
        conclusion = CONCLUSION_INCONCLUSIVE
    else:
        conclusion = CONCLUSION_NONCONFORMING
    reason = (
        f"decision rests on MAD={mad:.4f} ({band}; Nigrini 2012 bands). "
        f"Chi-square {chi:.2f} (df={df}, p={p:.4f}) is reported alongside "
        f"but does not decide: its power grows with n, so at ledger scale "
        f"it rejects deviations too small to matter."
    )
    return BenfordResult(
        test=test,
        applicable=True,
        refusal_reason="",
        n=n,
        counts=observed,
        expected_proportions=expected,
        digit_measurements=measurements,
        chi_square=chi,
        chi_square_df=df,
        p_value=p,
        mad=mad,
        mad_band=band,
        conclusion=conclusion,
        conclusion_reason=reason,
    )


def first_digit_test(
    amounts_cents,
    min_n: int = 300,
    span_min: float = 100.0,
    max_mode_share: float = 0.05,
    confidence: float = DEFAULT_CONFIDENCE,
) -> BenfordResult:
    amounts = [a for a in amounts_cents if a > 0]
    refusal = _guard(amounts, min_n, span_min, max_mode_share, "first_digit")
    if refusal is not None:
        return refusal
    return _run(
        "first_digit",
        (first_digit(a) for a in amounts),
        benford_first_expected(),
        MAD_BANDS_FIRST,
        confidence,
    )


def second_digit_test(
    amounts_cents,
    min_n: int = 300,
    span_min: float = 100.0,
    max_mode_share: float = 0.05,
    confidence: float = DEFAULT_CONFIDENCE,
) -> BenfordResult:
    amounts = [a for a in amounts_cents if a > 0 and second_digit(a) is not None]
    refusal = _guard(amounts, min_n, span_min, max_mode_share, "second_digit")
    if refusal is not None:
        return refusal
    return _run(
        "second_digit",
        (second_digit(a) for a in amounts),
        benford_second_expected(),
        MAD_BANDS_SECOND,
        confidence,
    )


def benford_for_ledger(ledger, **kwargs) -> dict:
    """Both digit tests over entry amounts. Returns {"first_digit": ...,
    "second_digit": ...}."""
    amounts = [e.amount_cents for e in ledger.entries]
    return {
        "first_digit": first_digit_test(amounts, **kwargs),
        "second_digit": second_digit_test(amounts, **kwargs),
    }
