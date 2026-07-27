# Decision Ledger

Append as you go. Cite inherited decisions from ../ai-audit-toolkit/DECISIONS.md
by number when adopting them.

## D-001 · 2026-07-27 · Synthetic data only, forever
No real company or client data enters this repo under any circumstances — not
anonymized, not aggregated, not "just structure". The generator is the only
data source. This is what makes the repo publishable by a working auditor.

## D-002 · 2026-07-27 · Planted truth is the epistemic foundation
Every detection capability is graded against ledgers whose anomalies are known
by construction (the injector manifest). A rule without a report-card entry is
a claim without evidence. (Same discipline as the crypto lab's planted-drift
tests and the toolkit's scripted-endpoint fixtures.)

## D-003 · 2026-07-27 · Leads, not conclusions
Analytics direct attention; auditors conclude. Renderer language is guarded by
test: outputs speak of exceptions, indicators, and leads for follow-up — never
"fraud", never "violation" as a determination.

## D-004 · 2026-07-27 · Inherited uncertainty discipline
Per toolkit D-008/D-011: every rate is a Measurement with interval, method,
and n; decisions compare intervals to thresholds and may return inconclusive.
Re-implemented here, not imported.

## D-005 · 2026-07-27 · Formulas, not tables
Sampling sizes and evaluation limits are computed from binomial /
hypergeometric first principles. Published lookup tables are copyrighted
compilations and are never transcribed; agreement with them is a test of the
math, not a source of it.

## D-006 · 2026-07-27 · Money is integer cents
Float money is a rounding bug factory. All amounts are int cents end to end;
Benford digit extraction is unaffected because leading significant digits are
invariant under the ×100 scale. The model validates structure only (one-sided
non-negative lines) and deliberately *permits* anomalies — unbalanced entries,
blank descriptions, self-approval — since a model that refused to represent
them could never carry a plant to the rule that must find it.

## D-007 · 2026-07-27 · Determinism is byte identity through canonical JSON
Per toolkit D-009, re-implemented: one pinned encoding (sorted keys, tight
separators, ASCII, NaN rejected) with a known-vector test, and "same seed →
same ledger" is asserted as equality of canonical bytes, not of summaries.
CSV output uses explicit LF terminators so the guarantee holds across
platforms. RNG streams are seeded from strings (`"{seed}/gl"`), which CPython
hashes stably across platforms and versions.

## D-008 · 2026-07-27 · The clean ledger is realistic, not sterile
The clean population deliberately contains benign structure that resembles
anomaly conditions: an exactly-$9,000 recurring rent (round-dollar), system
month-end batches that land on weekends, a December posting cluster
(period-end pressure). Without these, report-card precision would be 1.0 by
construction and would demonstrate nothing. Conversely, stochastic amounts
always carry non-zero cents, so every clean round-dollar hit traces to a
named benign source. Base rates are pinned by test (FY2025 defaults: exactly
12 multiple-of-$1,000 entries, all rent; exactly 6 weekend postings, all
system batch; year-end 5-business-day window under 8% of entries).

## D-009 · 2026-07-27 · Planted entries carry no positional artifact
Injection happens before ids exist: clean and planted raw entries are merged,
every entry gets a shuffled within-date rank, and ids are issued in
(posting_date, rank) order. A detector cannot recover ground truth from id
gaps, suffixes, or intra-day position. The manifest (which ids constitute
each anomaly, and why) is the only record of truth — per D-002 it is the
epistemic foundation, so it must not leak into the data.

## D-010 · 2026-07-27 · The injector has its own RNG stream
Anomalies draw from `Random("{seed}/anomalies")`, never from the generator's
stream, so changing the anomaly plan can never reshuffle the clean
population. Tested: clean generation is byte-identical before and after an
injection run. This is what lets Phase 3 compare "same ledger, different
plants" meaningfully. Property tests assert every planted class actually has
the property its manifest note claims — plants that drift from their own
description would silently corrupt every recall number downstream.
