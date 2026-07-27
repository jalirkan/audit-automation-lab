# Example run — committed end-to-end demonstration

Everything in this directory regenerates deterministically from one command
(`python cli.py example`); `ledger.json` and `ledger.csv` are gitignored
because they are large and fully determined by the seed. Nothing here is
real data (DECISIONS D-001).

## The ledger under test

- 100051 journal entries, FY2025, generator seed 20260401
- 43 planted anomalies across 11 classes,
  spanning 59 entries (`manifest.json` is the ground truth)
- battery yield: 2256 flags over 2242
  distinct entries (`flags.json`; 14 workpapers in `workpapers/`)

## The report card (the honesty layer)

Measured against planted truth on separate ledgers
(20000 entries x 5 seeds, richer
plan for statistical power — full tables in `report-card.md`):

- dormant_reactivation: 40/40 detected, recall 1.0000 (95% wilson 0.9124-1.0000, n=40) -> pass
- duplicate_pair: 40/40 detected, recall 1.0000 (95% wilson 0.9124-1.0000, n=40) -> pass
- late_round_dollar: 40/40 detected, recall 1.0000 (95% wilson 0.9124-1.0000, n=40) -> pass
- missing_description: 40/40 detected, recall 1.0000 (95% wilson 0.9124-1.0000, n=40) -> pass
- near_duplicate: 39/40 detected, recall 0.9750 (95% wilson 0.8712-0.9956, n=40) -> inconclusive
- post_close_entry: 40/40 detected, recall 1.0000 (95% wilson 0.9124-1.0000, n=40) -> pass
- self_approval: 40/40 detected, recall 1.0000 (95% wilson 0.9124-1.0000, n=40) -> pass
- threshold_shaving: 40/40 detected, recall 1.0000 (95% wilson 0.9124-1.0000, n=40) -> pass
- unbalanced_entry: 40/40 detected, recall 1.0000 (95% wilson 0.9124-1.0000, n=40) -> pass
- unusual_pairing: 15/15 detected, recall 1.0000 (95% wilson 0.7961-1.0000, n=15) -> inconclusive
- weekend_manual: 40/40 detected, recall 1.0000 (95% wilson 0.9124-1.0000, n=40) -> pass

- battery precision: 0.2049 (95% wilson 0.1904-0.2203, n=2796) -> exception
- false positives: 222.48 per 10k clean entries
  (interval 213.5-231.8 per 10k, n=99920)

An unflattering precision outcome against the demo target is the card doing
its job: the per-rule table in `report-card.md` shows which screens buy
their recall cheaply and which sweep in review populations (period-end
selection is the dominant cost, by design of the procedure). Leads, not
conclusions, throughout.
