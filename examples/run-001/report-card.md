# Detection report card

The lab grades itself before it grades a ledger: every rule ran against synthetic ledgers whose anomalies are known by construction (the injector manifest is the ground truth), and the rates below are measured against that truth. A detection capability without such a report card is a claim without evidence.

## Definitions

| | |
|---|---|
| detected | an instance counts as detected when any rule flags any of its entry ids |
| fp_rate | flagged clean entries / clean entries (also shown per 10,000) |
| note | targets are engagement parameters, not standards; outcomes are decided interval-vs-target, so small planted counts yield inconclusive, not a pass |
| precision | flagged entries that are planted / all flagged entries |

## Targets

| | |
|---|---|
| Recall floor (per class) | 0.9 |
| Precision floor | 0.5 |
| False-positive ceiling | 0.02 |
| Minimum pooled sample for a pass | 20 |
| Caveat | targets are engagement parameters chosen for this lab, not professional standards |

## Recall by planted class (pooled across seeds)

*Seeds: 8101, 8102, 8103, 8104, 8105*

| Class | Planted | Detected | Recall (Wilson) | Outcome | Per-seed range |
|---|---|---|---|---|---|
| dormant_reactivation | 40 | 40 | 1.0000 (95% wilson 0.9124-1.0000, n=40) | pass | 1.00-1.00 |
| duplicate_pair | 40 | 40 | 1.0000 (95% wilson 0.9124-1.0000, n=40) | pass | 1.00-1.00 |
| late_round_dollar | 40 | 40 | 1.0000 (95% wilson 0.9124-1.0000, n=40) | pass | 1.00-1.00 |
| missing_description | 40 | 40 | 1.0000 (95% wilson 0.9124-1.0000, n=40) | pass | 1.00-1.00 |
| near_duplicate | 40 | 39 | 0.9750 (95% wilson 0.8712-0.9956, n=40) | inconclusive | 0.88-1.00 |
| post_close_entry | 40 | 40 | 1.0000 (95% wilson 0.9124-1.0000, n=40) | pass | 1.00-1.00 |
| self_approval | 40 | 40 | 1.0000 (95% wilson 0.9124-1.0000, n=40) | pass | 1.00-1.00 |
| threshold_shaving | 40 | 40 | 1.0000 (95% wilson 0.9124-1.0000, n=40) | pass | 1.00-1.00 |
| unbalanced_entry | 40 | 40 | 1.0000 (95% wilson 0.9124-1.0000, n=40) | pass | 1.00-1.00 |
| unusual_pairing | 15 | 15 | 1.0000 (95% wilson 0.7961-1.0000, n=15) | inconclusive | 1.00-1.00 |
| weekend_manual | 40 | 40 | 1.0000 (95% wilson 0.9124-1.0000, n=40) | pass | 1.00-1.00 |

## Battery precision and false-positive load

| | |
|---|---|
| Precision (entry level) | 0.2049 (95% wilson 0.1904-0.2203, n=2796) |
| Precision outcome | exception — entire interval below threshold |
| False-positive rate | 0.0222 (95% wilson 0.0214-0.0232, n=99920) |
| False positives per 10,000 clean entries | 222.5 (interval 213.5-231.8 per 10k, n=99920) |
| FP outcome | exception — entire interval above threshold |

## Per-rule precision (pooled)

*Clean hits are the cost side of each rule: legitimate entries swept in as leads*

| Rule | Flags | Planted hits | Clean hits | Precision (Wilson) |
|---|---|---|---|---|
| R-001 | 40 | 40 | 0 | 1.0000 (95% wilson 0.9124-1.0000, n=40) |
| R-002 | 1682 | 82 | 1600 | 0.0488 (95% wilson 0.0394-0.0601, n=1682) |
| R-003 | 70 | 40 | 30 | 0.5714 (95% wilson 0.4548-0.6806, n=70) |
| R-004 | 100 | 40 | 60 | 0.4000 (95% wilson 0.3094-0.4980, n=100) |
| R-005 | 646 | 120 | 526 | 0.1858 (95% wilson 0.1577-0.2176, n=646) |
| R-006 | 40 | 40 | 0 | 1.0000 (95% wilson 0.9124-1.0000, n=40) |
| R-007 | 40 | 40 | 0 | 1.0000 (95% wilson 0.9124-1.0000, n=40) |
| R-008 | 16 | 16 | 0 | 1.0000 (95% wilson 0.8064-1.0000, n=16) |
| R-009 | 40 | 40 | 0 | 1.0000 (95% wilson 0.9124-1.0000, n=40) |
| R-010 | 98 | 94 | 4 | 0.9592 (95% wilson 0.8997-0.9840, n=98) |
| R-011 | 92 | 78 | 14 | 0.8478 (95% wilson 0.7606-0.9071, n=92) |

## Per-run summary

| Seed | Entries | Planted instances | Flagged | Precision | FP load |
|---|---|---|---|---|---|
| 8101 | 20099 | 83 | 561 | 0.2050 (95% wilson 0.1736-0.2403, n=561) | 223.2/10k (n=19984) |
| 8102 | 20099 | 83 | 517 | 0.2224 (95% wilson 0.1887-0.2603, n=517) | 201.2/10k (n=19984) |
| 8103 | 20099 | 83 | 586 | 0.1928 (95% wilson 0.1629-0.2267, n=586) | 236.7/10k (n=19984) |
| 8104 | 20099 | 83 | 573 | 0.2007 (95% wilson 0.1699-0.2354, n=573) | 229.2/10k (n=19984) |
| 8105 | 20099 | 83 | 559 | 0.2057 (95% wilson 0.1743-0.2412, n=559) | 222.2/10k (n=19984) |

## Missed instances

| Seed | Class | Anomaly |
|---|---|---|
| 8103 | near_duplicate | AN-036 |

## Reading this card

Outcomes are decided by comparing the Wilson interval to the target, never the point estimate: a class caught 6 times out of 6 planted renders inconclusive against a 0.9 floor, because six instances cannot demonstrate it. Inconclusive is reported, never rounded up to pass.

Precision is deliberately not 1.0: the clean population contains benign structure (recurring round-dollar rent, system batches posting on weekend month-ends, a December close cluster) precisely so the false-positive cost of each rule is measured rather than assumed away.
