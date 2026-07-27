# Workpaper WP-SAMPLING — Attribute sampling

## Bridge from full-population analytics

The rule battery is a complete examination that stratifies the population into flagged and unflagged entries; it is not a sample and supports no projection beyond itself. Where the audit response to a flagged stratum is manual review of a random sample drawn from that stratum, the attribute-sampling mathematics here quantifies what that sample supports about the stratum at a stated risk of overreliance — and nothing more.

## Sample size (attribute sampling)

| | |
|---|---|
| Tolerable deviation rate | 0.0500 |
| Expected deviation rate | 0.0000 |
| Risk of overreliance | 0.0500 |
| Population | large (binomial) |
| Required sample size | n=59 |
| Planned deviation allowance | 0 |
| Achieved risk at n | 0.0485 |
| Method | binomial, computed from the defining inequality (no table lookup) |

## Sample evaluation

| | |
|---|---|
| Sample | 0 deviations in n=59 |
| Observed rate | 0.0000 |
| Upper deviation limit | at 95% one-sided confidence, the deviation rate does not exceed 0.0495 (sample: 0/59, n=59) |
| Tolerable rate | 0.0500 |
| Outcome | pass |
| Basis | UDL 0.0495 <= tolerable 0.0500: the sample (n=59) supports reliance at 95% one-sided confidence |

Flags in this pack are leads for auditor follow-up. A flag directs attention; it does not, by itself, establish error or irregularity, and no automated procedure here reaches a conclusion about intent. Disposition requires auditor judgment and further procedures.
