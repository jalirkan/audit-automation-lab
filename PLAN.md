# Build Plan — Audit Automation Lab

Phased roadmap for mostly-autonomous execution. Each phase ends with passing
tests and a commit. Before writing any code, read
`../ai-audit-toolkit/DECISIONS.md` end to end: that project solved the
evidence/uncertainty/reporting problems this one shares. **Borrow the
decisions, not the code** — re-implement cleanly here (no cross-repo imports);
where you adopt one of its decisions, cite it in this repo's DECISIONS.md
(e.g. "per toolkit D-008, Wilson intervals for proportions").

## Conventions

- Python stdlib only; kebab-case dirs, snake_case modules; unit tests for
  every non-trivial module; `python -m unittest discover -s tests -t .` green
  before every commit.
- Determinism everywhere: generators and analytics take explicit seeds; two
  runs with the same seed produce byte-identical outputs.
- Every reported rate carries interval + n. Three outcomes: pass / exception /
  inconclusive. No composite "risk scores" that average unlike things.
- Standards (AU-C 240, ISA 240, AICPA sampling guidance) are referenced by ID
  with original one-line summaries. Formulas are computed from first
  principles; copyrighted tables are never transcribed.
- Findings language: analytics produce **leads**, auditors produce
  conclusions. Renderers must never emit "fraud detected".

## Phase 0 — Synthetic ledger foundation
- `ledger/`: chart of accounts model; deterministic GL generator — configurable
  entry count, date range, seasonality (month-end spikes), user population,
  approval workflow fields, amount distributions per account class.
- `ledger/anomalies.py`: planted-anomaly injector with a manifest — each
  scenario (late round-dollar entry, SoD conflict, duplicate pair,
  threshold-shaving series, dormant reactivation…) records exactly which
  entry ids constitute the anomaly. The manifest IS the ground truth.
- Tests: same seed → identical ledger; manifest ids exist; anomaly-free
  generation contains no accidental rule triggers above a documented base rate.

## Phase 1 — Rule engine (deterministic JE tests)
- `rules/`: each rule = id, population definition, criterion, `evaluate(ledger)
  → exceptions` with per-entry rationale. Ship: unbalanced entry, period-end
  posting, weekend/holiday posting, round-dollar, just-below-threshold,
  missing/short description, dormant-account reactivation, unusual
  account-pairing (learned from the population itself — document the
  no-lookahead framing), self-approval SoD, duplicate & near-duplicate.
- Tests: every rule against a fixture that triggers it and one that doesn't.

## Phase 2 — Statistical layer
- `analytics/benford.py`: first- and second-digit tests, chi-square and MAD
  with stated thresholds and their provenance; applicability guard (Benford
  assumptions — span of magnitudes, no assigned numbers) that refuses to
  opine when preconditions fail rather than emitting a bogus p-value.
- `analytics/profile.py`: population profiling (volume by day/user/account,
  amount distributions) for the drift phase later.
- Tests: Benford on conforming synthetic data passes; on planted non-conforming
  data fails; applicability guard triggers on assigned-number populations.

## Phase 3 — Detection report card (the centerpiece)
- `reportcard/`: run all rules + analytics against ledgers with planted
  manifests → per-anomaly-class recall, overall precision, false-positive
  rate per 10k entries — all with Wilson intervals. Multiple seeds → stability.
- This is the honesty layer: the lab grades itself before grading ledgers.
- Tests: report card math against hand-computed small cases; a deliberately
  broken rule shows degraded recall (the report card catches regressions).

## Phase 4 — Attribute sampling bridge
- `sampling/`: attribute-sample size and evaluation from first-principles
  binomial/hypergeometric math (compute, don't transcribe tables): sample
  size for tolerable/expected deviation, upper deviation limit from results.
- Bridge narrative: full-population analytics select and stratify; sampling
  math quantifies what a manual-review sample of the flagged strata supports.
- Tests: known textbook-style cases computed from formulas match the math.

## Phase 5 — Workpapers + lead sheets
- `report/`: per-rule workpaper (population, procedure, criterion, exceptions
  with entry detail, limitations, conclusion-as-lead), engagement summary
  lead sheet, and the detection report card rendered alongside — Markdown +
  standalone HTML. Language guard test: no prohibited conclusory phrases.

## Phase 6 — CLI + end-to-end example
- `cli.py`: `generate`, `test <ledger>`, `reportcard`, `sample-size`,
  `report <run>`. `examples/`: committed end-to-end run — 100k-entry ledger,
  ~40 planted anomalies across classes, full workpaper pack + report card.
- README quick-start showing one command producing the whole pack.

## Stretch
- Continuous mode: monthly batches, profile drift vs baseline, exception aging.
  **Done** — `continuous/` (batching, drift, aging), `ledger/drift.py`
  (planted drift, the ground truth), `rules/drift.py` (R-012, its own
  battery), graded by the existing report card via its `generate` hook. See
  DECISIONS D-027 to D-031. Deliberately left for a later pass: drift in
  amount *distribution* rather than composition (the profile carries
  deciles; comparing them needs a distributional statistic and its own
  calibration), a rolling rather than fixed baseline, and drift planted
  *inside* the baseline window — the case this screen provably cannot see.
- AP/AR subledger scenarios (duplicate invoices, ghost vendors) on the same
  planted-truth discipline. **AP duplicate invoices done** — `ledger/ap.py`
  (the subledger generator, its documented benign structure, and four
  planted duplicate classes), `rules/ap.py` (AP-001 on the document key,
  AP-002 on amount and invoice date, in their own battery), graded by the
  existing report card through its `generate` hook. See DECISIONS D-033 to
  D-035. Deliberately left for a later pass: re-keys whose *amount* was
  altered (both screens require equal amounts and say so), the same invoice
  paid twice through two payment documents rather than recorded twice,
  duplicates spanning two vendor records that are really one vendor, ghost
  vendors, and the entire AR side — each needs its own plant and its own
  evidence, and an unplanted class would be an unmeasured claim.
- Optional LLM assist (adapter-gated like the toolkit): natural-language
  rationale summaries for flagged entries — never as the detector, only as
  the explainer, and clearly labeled.

## Definition of done (v1)
One command generates a realistic synthetic ledger with planted anomalies;
one command runs the full battery and emits workpapers, a lead sheet, and a
detection report card with intervals; the report card demonstrates ≥ stated
recall on every planted class or documents why not. Everything offline,
deterministic, and reviewable.
