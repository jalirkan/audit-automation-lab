# Audit Automation Lab

The mirror image of [ai-audit-toolkit](../ai-audit-toolkit): that project audits
AI systems; this one is AI-era tooling that *performs* audit procedures.
Full-population journal-entry testing, classical audit analytics, and generated
workpapers — demonstrated entirely on synthetic data, and graded against
planted ground truth so the tool's own detection performance is measured, not
asserted.

**The thesis:** the traditional audit tests 25 sampled transactions because a
human can't read 400,000. Software can read all 400,000 — but full-population
testing is only trustworthy if the tester's error rates are themselves known.
So every analytic here ships with a report card: synthetic ledgers with known
planted anomalies, and the recall/precision the engine actually achieved
against them, with confidence intervals.

## What it will do (see PLAN.md)

- **Synthetic ledger generator** — deterministic, seeded general ledgers with
  configurable size, seasonality, and planted anomaly scenarios. No real
  company data, ever; that constraint is what makes the repo public-safe.
- **Journal-entry testing engine** — the canonical procedure (AU-C 240 / ISA
  240 territory), as a library of explicit rules: period-end and weekend
  postings, round-dollar entries, dormant-account reactivation,
  just-below-threshold amounts, segregation-of-duties conflicts, duplicate and
  near-duplicate detection, missing descriptions, unusual account pairings.
- **Statistical layer** — Benford first/second-digit conformity with proper
  test statistics, population profiling, outlier scoring. Every rate carries
  its interval and sample size.
- **Detection report card** — recall and precision against planted truth, by
  anomaly class, with Wilson intervals. The lab grades itself before it grades
  a ledger.
- **Workpapers** — population, procedure, criterion, exceptions, and
  conclusion per test; a lead-sheet style summary; findings framed as *leads
  for auditor judgment*, never as automated conclusions of fraud.

## Principles

Inherited from the toolkit next door, deliberately: stdlib-only Python,
everything offline and deterministic, uncertainty mandatory on every reported
rate, three outcomes (pass / exception / inconclusive), original text only
(standards referenced by ID, formulas computed rather than copied from
copyrighted tables), and flags are leads — an analytic can direct attention,
only an auditor can conclude.

*Educational/professional tooling on synthetic data; not audit software for
production use without professional supervision.*
