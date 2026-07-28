# Audit Automation Lab

The mirror image of [ai-audit-toolkit](https://github.com/jalirkan/ai-audit-toolkit): that project audits
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

## What it does (v1 complete — phases 0-6 of PLAN.md)

- **Synthetic ledger generator** (`ledger/`) — deterministic, seeded general
  ledgers: seasonality, approval workflow, per-class amount distributions,
  and *documented benign structure* (recurring round-dollar rent, weekend
  system batches, a December close cluster) so precision measurements mean
  something. Planted-anomaly injector whose manifest is the ground truth.
- **Journal-entry testing engine** (`rules/`) — eleven explicit rules
  (AU-C 240 / ISA 240 territory): unbalanced, period-end/post-close,
  weekend-holiday, round-dollar, just-below-threshold, short description,
  dormant reactivation, rare account pairing, self-approval, duplicate,
  near-duplicate. Each declares population, criterion, and limitations, and
  produces per-entry rationales.
- **Statistical layer** (`core/stats.py`, `analytics/`) — Wilson intervals
  enforced at construction, three-outcome decisions against the interval,
  Benford first/second-digit tests (MAD decides, chi-square reported, guard
  refuses inapplicable populations), population profiling.
- **Detection report card** (`reportcard/`) — recall by planted class,
  entry-level precision, false positives per 10k clean entries, pooled
  across seeds with per-seed stability. The lab grades itself before it
  grades a ledger, and small pools render *inconclusive*, not a hollow pass.
- **Attribute sampling** (`sampling/`) — sample sizes and upper deviation
  limits computed from binomial/hypergeometric first principles; classic
  table values are reproduced as tests of the math, never transcribed.
- **Workpapers** (`report/`) — population, procedure, criterion, exceptions,
  limitations, conclusion-as-lead per test; engagement lead sheet; report
  card rendered alongside; Markdown + self-contained HTML. A renderer-level
  guard refuses conclusory language, and a scanner rejects any percentage
  that appears without its sample size.

## Quick start

```
python -m unittest discover -s tests -t .   # 186 tests, ~15 seconds
python cli.py example                        # regenerate examples/run-001 end to end
```

The committed example (`examples/run-001/`) is a 100,051-entry FY2025 ledger
with 43 planted anomalies: manifest, flags, 14 workpapers, and the report
card, all regenerated deterministically from seeds (the large raw ledger
files are gitignored and rebuild byte-identically). Highlights from its
report card: nine anomaly classes pass a 0.9 recall floor at n=40 with
Wilson intervals; near-duplicate shows an honest gap (39/40 — sub-$100
shifts fall outside the 1% amount tolerance); battery precision 0.20
(0.19-0.22, n=2796) takes an *exception* against the demo target, dominated
by the period-end and below-threshold screens, whose yield is a review
population by design. The per-rule table shows exactly which screen buys
its recall at what false-positive cost.

Other commands: `generate`, `test`, `report`, `reportcard`, `sample-size`
(see `python cli.py --help`).

## Principles

Inherited from the toolkit next door, deliberately: stdlib-only Python,
everything offline and deterministic, uncertainty mandatory on every reported
rate, three outcomes (pass / exception / inconclusive), original text only
(standards referenced by ID, formulas computed rather than copied from
copyrighted tables), and flags are leads — an analytic can direct attention,
only an auditor can conclude.

*Educational/professional tooling on synthetic data; not audit software for
production use without professional supervision.*
