# Engagement lead sheet — journal-entry testing

| | |
|---|---|
| Engagement | Synthetic ledger laboratory (all data generated; no client data exists in this repository) |
| Fiscal year | 2025-01-01 to 2025-12-31 |
| Generator | version 1, seed 20260401 |
| Ledger size | 100051 journal entries |
| Approval threshold | 10000.00 |

## Population overview

| | |
|---|---|
| Journal entries | 100051 |
| Journal lines | 200128 |
| Posting dates | 2025-01-02 to 2026-01-08 |
| By source | AP: 41962, AR: 3985, CR: 17902, GL: 14164, PAY: 26, REV: 21988, SYS: 24 |
| Entries requiring approval | 16862 |
| Approvals missing | 0 |

## Journal-entry tests

*Complete examinations; exception counts are exact*

| Rule | Title | Population | Exceptions | Outcome |
|---|---|---|---|---|
| R-001 | Unbalanced journal entries | 100051 | 4/100051 (0.00%) | exception |
| R-002 | Entries at or after fiscal year end | 100051 | 1523/100051 (1.52%) | exception |
| R-003 | Weekend and holiday postings | 100051 | 10/100051 (0.01%) | exception |
| R-004 | Large exact round-dollar entries | 57996 | 16/57996 (0.03%) | exception |
| R-005 | Amounts just below the approval threshold | 95724 | 559/95724 (0.58%) | exception |
| R-006 | Missing or uninformative descriptions | 100051 | 4/100051 (0.00%) | exception |
| R-007 | Postings to dormant accounts | 100051 | 4/100051 (0.00%) | exception |
| R-008 | Unusual account pairings | 100051 | 5/100051 (0.00%) | exception |
| R-009 | Approval segregation of duties | 16862 | 4/16862 (0.02%) | exception |
| R-010 | Duplicate entries | 100051 | 32/100051 (0.03%) | exception |
| R-011 | Near-duplicate entries (shifted resubmissions) | 100051 | 95/100051 (0.09%) | exception |

## Digit conformity

| Test | Amounts | MAD | Band | Conclusion |
|---|---|---|---|---|
| first digit | n=100051 | 0.0018 | close conformity | conforming |
| second digit | n=100051 | 0.0007 | close conformity | conforming |

## Lead summary

Distinct entries flagged by at least one rule: 2242 of 100051 (2.24% of the ledger, n=100051).

Flags in this pack are leads for auditor follow-up. A flag directs attention; it does not, by itself, establish error or irregularity, and no automated procedure here reaches a conclusion about intent. Disposition requires auditor judgment and further procedures.
