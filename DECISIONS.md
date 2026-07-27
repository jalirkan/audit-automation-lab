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

## D-011 · 2026-07-27 · Inapplicability is a first-class rule outcome
A rule can refuse to run — `applicable()` returns why — instead of producing
meaningless output: rare-pairing below its minimum population (everything
looks rare), threshold rules with no threshold in metadata. Refusal renders
as an inconclusive procedure, never a pass. This also adopts toolkit D-020's
lesson in rule form: a missing configuration means *refuse*, not *assume a
default and silently test something the auditor didn't configure*.

## D-012 · 2026-07-27 · Period-end means the reporting period, not every month-end
R-002 targets the final business day(s) of the fiscal year plus post-close
entries (the AU-C 240 / ISA 240 emphasis), not every month-end. Month-end
close activity is the documented benign pressure the generator creates on
purpose (D-008); a rule that flagged every month-end would be a seasonality
detector, and its workpaper says the yield is a review population, not an
exception list.

## D-013 · 2026-07-27 · The pairing rule states its no-lookahead framing
R-008 learns pair frequencies from the same population it scores. That is
population profiling for lead generation — no train/test split exists and
none is claimed. A flag means "rare within this ledger", never "anomalous
against the world", and the limitation is printed in the workpaper, not
buried in a docstring (per toolkit D-015: screens are labelled as screens).
Near-duplicate similarity is likewise a lexical screen (difflib), labelled
as such.

## D-014 · 2026-07-27 · Rules are complete examinations, framed that way
Every rule examines 100% of its declared population (toolkit D-031,
re-implemented as framing): no rule samples, so no rule's flag count invites
projection to an unexamined remainder. Population definitions are metadata
on the rule and are rendered into the workpaper next to the counts, and
flags carry per-entry rationales specific enough to review without
re-deriving the analytic.
