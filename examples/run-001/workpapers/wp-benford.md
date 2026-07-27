# Workpaper WP-BENFORD — Digit conformity

| | |
|---|---|
| Engagement | Synthetic ledger laboratory (all data generated; no client data exists in this repository) |
| Fiscal year | 2025-01-01 to 2025-12-31 |
| Generator | version 1, seed 20260401 |
| Ledger size | 100051 journal entries |
| Approval threshold | 10000.00 |

## Benford first digit test

| | |
|---|---|
| Amounts tested | n=100051 |
| MAD | 0.0018 (close conformity) |
| Chi-square | 35.03 on 8 degrees of freedom, p=0.0000 (n=100051) |
| Conclusion | conforming |

decision rests on MAD=0.0018 (close conformity; Nigrini 2012 bands). Chi-square 35.03 (df=8, p=0.0000) is reported alongside but does not decide: its power grows with n, so at ledger scale it rejects deviations too small to matter.

| Digit | Observed count | Expected proportion | Observed proportion (with interval) |
|---|---|---|---|
| 1 | 30600 | 0.3010 | 0.3058 (95% wilson 0.3030-0.3087, n=100051) |
| 2 | 17964 | 0.1761 | 0.1795 (95% wilson 0.1772-0.1819, n=100051) |
| 3 | 12474 | 0.1249 | 0.1247 (95% wilson 0.1226-0.1267, n=100051) |
| 4 | 9447 | 0.0969 | 0.0944 (95% wilson 0.0926-0.0962, n=100051) |
| 5 | 7879 | 0.0792 | 0.0787 (95% wilson 0.0771-0.0804, n=100051) |
| 6 | 6539 | 0.0669 | 0.0654 (95% wilson 0.0638-0.0669, n=100051) |
| 7 | 5610 | 0.0580 | 0.0561 (95% wilson 0.0547-0.0575, n=100051) |
| 8 | 5087 | 0.0512 | 0.0508 (95% wilson 0.0495-0.0522, n=100051) |
| 9 | 4451 | 0.0458 | 0.0445 (95% wilson 0.0432-0.0458, n=100051) |

## Benford second digit test

| | |
|---|---|
| Amounts tested | n=100051 |
| MAD | 0.0007 (close conformity) |
| Chi-square | 11.88 on 9 degrees of freedom, p=0.2201 (n=100051) |
| Conclusion | conforming |

decision rests on MAD=0.0007 (close conformity; Nigrini 2012 bands). Chi-square 11.88 (df=9, p=0.2201) is reported alongside but does not decide: its power grows with n, so at ledger scale it rejects deviations too small to matter.

| Digit | Observed count | Expected proportion | Observed proportion (with interval) |
|---|---|---|---|
| 0 | 12293 | 0.1197 | 0.1229 (95% wilson 0.1208-0.1249, n=100051) |
| 1 | 11339 | 0.1139 | 0.1133 (95% wilson 0.1114-0.1153, n=100051) |
| 2 | 10837 | 0.1088 | 0.1083 (95% wilson 0.1064-0.1103, n=100051) |
| 3 | 10375 | 0.1043 | 0.1037 (95% wilson 0.1018-0.1056, n=100051) |
| 4 | 9895 | 0.1003 | 0.0989 (95% wilson 0.0971-0.1008, n=100051) |
| 5 | 9661 | 0.0967 | 0.0966 (95% wilson 0.0947-0.0984, n=100051) |
| 6 | 9335 | 0.0934 | 0.0933 (95% wilson 0.0915-0.0951, n=100051) |
| 7 | 9031 | 0.0904 | 0.0903 (95% wilson 0.0885-0.0921, n=100051) |
| 8 | 8816 | 0.0876 | 0.0881 (95% wilson 0.0864-0.0899, n=100051) |
| 9 | 8469 | 0.0850 | 0.0846 (95% wilson 0.0829-0.0864, n=100051) |

## Conclusion (as lead)

Digit-conformity results are population-level leads: a departure directs attention to the strata that drive it and is not an assertion about any individual entry.

Flags in this pack are leads for auditor follow-up. A flag directs attention; it does not, by itself, establish error or irregularity, and no automated procedure here reaches a conclusion about intent. Disposition requires auditor judgment and further procedures.
