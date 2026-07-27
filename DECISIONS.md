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

## D-015 · 2026-07-27 · Uncertainty enforced at construction; decisions against the interval
Implements D-004 structurally, re-implementing toolkit D-008/D-011/D-012: a
proportion `Measurement` raises without interval, named method, confidence,
and n; `render()` is the sanctioned display and always includes n; n=0 is
"not tested" with interval [0,1], never "0%". Wilson is the default because
audit rates cluster at 0 and 1, where the normal approximation reports zero
width. `decide()` compares the interval to the threshold with three outcomes
(pass / exception / inconclusive); min_sample gates only the pass; a
zero-tolerance threshold switches to the attribute rule (any exception is an
exception; a clean sample passes once n meets the minimum, interval reported
alongside). Boundary counts (0 or n successes) pin their exact bound to 0.0
or 1.0 rather than carrying float dust.

## D-016 · 2026-07-27 · Benford decisions rest on MAD; chi-square is reported, not the decider
Chi-square power grows with n: at ledger scale it rejects deviations far too
small to matter, so conformity is judged on MAD against the Nigrini (2012)
bands (cited as research constants; band values restated as numbers, and the
survival function computed from the incomplete gamma per D-005 — no table
transcription anywhere). The p-value is printed alongside with the reason it
does not decide. Marginal MAD renders inconclusive, not a soft pass. Each
digit's observed proportion is a full Measurement with its Wilson interval.

## D-017 · 2026-07-27 · The Benford guard refuses rather than opines
When preconditions fail — under 300 usable amounts, span of magnitudes below
×100, or a repeated identical amount above 5% of the population (assigned or
contractual numbers) — the test returns applicable=False with the reason and
no p-value or MAD at all. A fabricated p-value on inapplicable data is the
statistical version of the bug D-011 guards against. Found while testing:
the first "nonconforming" fixture spanned only ×10 and the guard refused it
— the fixture was wrong, not the guard; test data must earn applicability
before it can fail conformity.

## D-018 · 2026-07-27 · The generated ledger is empirically Benford-conforming
Measured, not assumed: at seed 42, first-digit MAD is 0.0117 (acceptable) at
900 entries and 0.0036 (close) at 5,000 — the lognormal amount mixture spans
enough magnitudes to conform. Conforming fixtures for tests are constructed
log-uniform (Benford by construction); non-conforming fixtures are
linear-uniform across three decades. The workpaper reports whatever the
ledger under test actually shows.

## D-019 · 2026-07-27 · Report-card definitions are pinned in one docstring
"Detected" = any rule flags any constituent entry id (with designed-rule
recall reported alongside); precision is entry-level against the planted
set; the FP denominator is clean entries only. These definitions decide
every number on the card, so they live in one place, are restated in the
rendered output, and the hand-computed unit test locks them (planted pair
originals count as planted — flagging the original of a duplicate is
correct detection, not a false positive). No wall-clock timestamps
anywhere in card output: identity is seeds + config echo, preserving the
byte-identity contract (D-007).

## D-020 · 2026-07-27 · Small planted pools yield inconclusive, and that is the point
Recall outcomes come from `decide()` against the interval (D-015): with the
default plan and three seeds, 6/6 caught cannot clear a 0.9 floor at 95%,
and the card says inconclusive rather than parading a hollow 100%. Passing
a 0.9 recall floor on clean detections alone needs ~35 pooled instances
(Wilson lower bound of n/n first reaches 0.9 near n=35) — the example run
sizes its plan accordingly. Measured at seeds 301-303, n=1000: battery
precision 0.36 (95% Wilson 0.30-0.42), FP 535 per 10k clean entries —
deliberately unflattering, driven by the benign structure D-008 plants:
the December window in R-002, rents in R-004, system weekend batches in
R-003, lexical near-duplicate candidates in R-011. A card that showed
precision 1.0 would mean the synthetic world was too easy to mean anything.

## D-021 · 2026-07-27 · The report card is the regression detector
A test removes the only rule designed for a class and asserts the card
drives that class's pooled recall to 0 with an exception outcome, while
intact classes stay caught (same discipline as the toolkit's planted-drift
validation, D-022/D-023 there: a detector that never fires would pass every
happy-path test).

## D-022 · 2026-07-27 · Sampling conventions pinned; the bridge is one honest sentence
Implements D-005. Planning: allowance c = expected deviations rounded up;
smallest n with P(X<=c | tolerable) <= risk; the hypergeometric form marks
K = ceil(tolerable x N) population items. Evaluation: exact one-sided upper
deviation limit (smallest rate leaving <= risk probability of a result this
clean), bisected on the binomial CDF with a fixed iteration count so output
is deterministic; finite populations bound whole deviant items (smallest
integer K). Three outcomes mirror D-015: UDL <= tolerable passes; observed
rate >= tolerable is an exception; in between, the sample size cannot
answer and says so. The classic anchors (59 at 5/5/0, 22 at 10/10/0, 93
with allowance 1 at 5%/5%/1%) are recomputed in tests from the formulas —
agreement with published tables is a test of the math, never a source.
BRIDGE_NOTE states the only legitimate connection to the rule battery: a
complete examination stratifies; sampling math describes what a random
sample *of a stratum* supports; a full-population screen is never recast
as a statistical sample after the fact (toolkit D-031's lesson applied to
sampling).

## D-025 · 2026-07-27 · Pair screens are density-dependent; R-011 keys on references
Found by the 100k example, not by unit tests: the similarity-based
near-duplicate screen produced 5,328 flags at ledger scale — templated
wording (same-customer receipts, same-vendor invoices) clears any fuzzy
bar once groups are dense, because candidate pairs grow with the square of
group size. Redesigned around how real AP dedup works: a pair flags when
amounts are close-but-unequal AND the descriptions share the same
*reference tokens* (digit runs like invoice or check numbers — excluding
the entry's own account ids, which reclass wording embeds), or wording is
nearly identical with no conflicting references. Differing references veto
the pair (different documents legitimately read alike); identical
referenceless prose with different amounts is deliberately unflagged
(repeated payments on account are routine). Result: 5,328 → 95 flags, with
recall preserved except one honest miss the card now displays — sub-$100
resubmissions whose fixed $1 shift exceeds the 1% amount tolerance
(39/40, inconclusive against the 0.9 floor). The gap stays visible rather
than being tuned away, and the rule's limitations say what the screen
cannot see.

## D-026 · 2026-07-27 · The committed example regenerates; big files don't get committed
`python cli.py example` rebuilds examples/run-001 in independent stages
(constrained shells can run them one at a time). The 100k-entry
ledger.json/csv are gitignored — they are pure functions of the seed —
while the manifest, flags, workpapers, report card and figures-bearing
README stay committed, with tests asserting internal consistency, both
language guards over every committed document, and byte-identical manifest
regeneration (toolkit D-034: committed artifacts and the code that makes
them must not diverge silently). Machine-scale JSON is written compact:
with indent, json.dumps falls back to the pure-Python encoder and turns a
100 MB ledger into minutes of serialization. Caveat recorded: per-platform
determinism is tested; cross-platform identity additionally assumes libm
rounds transcendentals identically (lognormal draws), which the
regeneration test would surface as a mismatch worth a human look. · 2026-07-27 · Exact counts state their n; intervals attach to inference
A rule battery is a census: 12 flags in 1,226 entries is a fact about this
ledger, not an estimate, and wrapping it in a Wilson interval would claim
sampling error that does not exist (toolkit D-031's distinction). So
workpapers report examination counts exactly, always with the population on
the same line, while intervals are mandatory wherever a number *is* an
inference — report-card rates (about the detection process across seeds),
Benford digit proportions (about the amount-generating process), and
sampling bounds. The rendered-output test enforces the line rule: any
numeric percentage must share its line with an n= or a k/n fraction, and a
companion test proves the scanner fires on a planted bare rate (toolkit
D-030 discipline). While building this, the scanner flagged the HTML
renderer's own stylesheet (width: 100%) — the CSS was changed rather than
the scanner weakened.

## D-024 · 2026-07-27 · One document model, two renderers, guards at the boundary
Per toolkit D-029: Markdown and standalone HTML render from one block
structure, so the formats cannot drift; the HTML embeds its CSS and fetches
nothing (tested: no http://, https://, <script, <link). Conclusory language
is refused *by the renderer* — not by convention — with a prohibited-phrase
list that bans conclusory collocations ("fraud detected", "is fraudulent",
"guilty") while leaving legitimate standard references ("the auditor's
consideration of fraud") renderable; companion tests prove the guard fires
in paragraphs and inside table cells. Workpapers carry no wall-clock
timestamps (D-019): identity is fiscal year, seeds, generator version.
Findings and scope limitations are listed separately on the lead sheet
(toolkit D-032): an inapplicable procedure renders as inconclusive with its
reason, never silently among passes.
