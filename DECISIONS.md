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

## D-023 · 2026-07-27 · Exact counts state their n; intervals attach to inference
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
regeneration test would surface as a mismatch worth a human look.

## D-027 · 2026-08-28 · Continuous mode batches on posting date; a batch is a sub-ledger
Monthly batching uses the **posting** date, not the effective date. A
monitor sees an entry when it hits the ledger, and the lag between the two
dates is the signal R-002 exists to notice: batching on the effective date
would file a January-posted, December-effective entry into December and
hide exactly the thing worth seeing. `JournalEntry.period` keeps its
effective-date meaning — the two are different questions, so the batcher
names its basis rather than reusing that property. A batch is not a new
type: it is a `Ledger` over a subset of entries with the parent's chart,
users and metadata, so every existing rule, the profiler and the report
card operate on a batch with no special case. The slice annotates its own
meta (`batch.parent_n_entries`) so a batch workpaper cannot claim the
parent's size, and batching is asserted to be a pure partition —
concatenating the batches in period order reproduces the parent exactly.

## D-028 · 2026-08-28 · Drift needs two gates, and the materiality floor is measured
A drift finding requires **both** an absolute share shift of at least
`min_shift` and non-overlapping Wilson intervals. Either alone is a bad
detector, for the two opposite reasons: the interval test alone repeats the
chi-square problem of D-016 (power grows with n until every wobble is
"significant"), and the floor alone would report shifts the data cannot
support. Non-overlap rather than "the baseline point estimate falls outside
the period interval", because the baseline is itself measured.

The 0.15 default is measured, not chosen for looks. Over 40 clean seeds ×
9 tested periods × 2 dimensions (≈3,900 cells, no plants anywhere): at
~100 entries per monthly batch the screen fires 32/3834 cells at a 0.10
floor, 21/3834 at 0.125, 5/3834 at 0.15 and 0/3834 at 0.20, with the
largest natural shift observed at 0.193; at ~200 entries per batch,
4/3960 at 0.10 and 0/3960 from 0.125 up (largest natural shift 0.109); at
~300 entries per batch, 0/3960 even at 0.10 (largest 0.088). So the honest
statement is a conditional one: at ~200 entries a month and up the default
is silent on clean populations, and the committed negative-control test
pins exactly that; at ~100 a month it is not silent, and the report card's
false-positive rate is where that cost shows up rather than being tuned
away. Planted drift is designed 0.22 above its baseline share with a 0.35
floor, so it clears the gate by design and the card measures whether the
design holds.

## D-029 · 2026-08-28 · Drift is graded by the same card, and its precision ceiling is published
Continuous mode did not get its own scorer. `build_report_card` takes the
planting function as a parameter, and drift is graded by the same pooling,
the same Wilson intervals, the same interval-vs-target decisions and the
same definitions as every anomaly class — a new capability scored by its
own bespoke metric is a claim graded by its author.

Two consequences are stated rather than engineered around. First, ground
truth is the entries that *constitute* the shift (the reassigned entries,
the added ones), never the whole drifted cell: counting a cell's
long-standing members as planted would flatter precision by construction.
Second, the screen concludes about a cell and names the cell's entries as
leads, so its entry-level precision is capped by the cell's composition —
measured at 0.66 (95% Wilson 0.63-0.68, n=1068) across three seeds, which
is the ceiling doing its work, not a defect. The rule's limitations say so
in the workpaper, and the card prints the number.

## D-030 · 2026-08-28 · Two batteries, graded apart
R-012 is not in `default_rules()`. It needs a year of monthly batches and a
baseline window that a single-period extract does not have, and no
point-in-time rule targets a drift class. Keeping the batteries separate is
also what keeps recall meaningful: measured on planted drift, the eleven
point-in-time rules catch 1/6 and 2/6 instances *incidentally* — a December
plant meets the period-end screen — so a mixed battery would credit drift
recall to rules that detected no drift at all. Graded honestly on its own,
the point-in-time battery takes an exception on every drift class, and that
is the correct result. Drift classes are likewise kept out of
`ANOMALY_CLASSES`: folding them into the default plan would book a
guaranteed zero-recall class onto a card that grades a different battery,
and would silently rewrite the committed example's ground truth.

## D-031 · 2026-08-28 · Aging reports elapsed time; it is not an open-items schedule
Exceptions are filed under the monthly batch they first appear in and aged
in whole periods against a reporting period — the batch is the unit of the
programme, so an exception in the batch just processed is age 0 whatever
day it posted. Entries posted after the reporting period are not aged at
all (a monitor running then has not seen them) and are counted separately
rather than folded into a bucket. What the schedule cannot say, it says
instead of implying: this lab has no disposition data — no clearing dates,
no reviewer sign-off — so *every* exception raised is aged, including any a
reviewer would already have cleared. Calling the result an open-items list
would be a claim the data cannot support, and the workpaper opens by
refusing that name. A companion note for anyone extending this: rules that
learn from the population they score (R-008, R-011) are different rules on
a monthly batch than on a year, because the batch is a different
population; aging therefore consumes the battery's flags over the
cumulative ledger rather than re-running it per batch.

## D-032 · 2026-08-28 · The verification runs where it can be checked
Until now every green run of the suite was somebody's local shell: a claim
with no evidence attached, in a repo whose whole argument is that detection
claims need evidence. CI runs the two documented commands unchanged —
`python -m unittest discover -s tests -t .` and `python cli.py example` —
and adds nothing of its own to make them pass. Three choices worth
recording. The suite runs across 3.10-3.13 because pyproject declares
`>=3.10`; the declared floor should be tested rather than assumed, and it
is where D-007's "stable across platforms and versions" claim about the
string-seeded streams stops being an assertion. The example job regenerates
the whole committed pack and diffs it against the tree (D-026's
non-divergence rule, applied to more than the manifest), pinned to one
interpreter so a red build means the generator changed and not that a
second libm rounded a lognormal draw differently. And there is no install
step: stdlib-only and offline are checkable properties, so the workflow is
built to fail if either stops being true rather than to describe them.

## D-033 · 2026-08-28 · A subledger is a Ledger with document fields; its battery is its own
The accounts-payable subledger is not a new type. `ledger/ap.py` builds a
`Ledger` — same chart, same users, same entries — so every existing rule,
the profiler, both renderers and the report card operate on it with no
special case, exactly as a monthly batch is just a smaller ledger (D-027).
A parallel stack for payables would have had to re-earn every guarantee
this one already has.

What a subledger genuinely adds is structure the general ledger does not
carry: `SourceDocument` (document type, vendor, the vendor's own reference,
the document date) on `JournalEntry`. The distinction is the point of the
scenario. A GL entry's counterparty and invoice number live in free text,
which is why the GL's near-duplicate screen is lexical and says so (D-013);
an AP extract has them as fields, and a detector built to scrape a vendor
name out of prose would be measuring the parser, not the control. The field
is optional and, when absent, is *absent from the serialization* rather than
emitted as null, so every general ledger written before subledgers existed
still has the canonical bytes it had (D-007). The CSV's four new columns are
appended for the same reason: no existing column moves.

So there are three batteries now, not two. `ap_rules()` refuses a general
ledger outright — no entry carries document fields, and a rule that cannot
read its population says why instead of examining nothing and passing
(D-011) — and no point-in-time rule targets an AP duplicate class. Graded on
the AP subledger anyway, the eleven GL rules catch 5 of 48 planted instances
across three seeds, all of them through R-010, which requires an identical
preparer *and* identical line structure: it sees neither the transposed
references nor the cross-period re-keys, at any window. That is D-030's
argument arriving a second time, and it is why the AP card grades the AP
battery alone.

## D-034 · 2026-08-28 · Four duplicate-invoice classes, because "duplicate" is four mechanisms
"Duplicate invoice" is not one thing, and planting it as one class would
have hidden the differences that matter. The four planted here are the same
event — one payable recorded twice — reached by four routes:

- `ap_exact_rekey`: same vendor, same reference, same invoice date, same
  amount, keyed a few days later.
- `ap_cross_period_rekey`: identical in kind, keyed 39 to 65 days later off
  a vendor statement.
- `ap_transposed_reference`: the re-key carries the classic keying error,
  two adjacent digits of the reference swapped.
- `ap_no_reference_match`: re-entered from a statement copy under a fresh
  internal reference, with the invoice date shifted by up to three days.

The test for a separate class was not taxonomy but **detectability**: a
mechanism earns its own class when some plausible mis-tuning of the screens
makes that mechanism, and only that mechanism, invisible. All four clear it,
and the report card is where each failure shows up (measured at seeds
601-602, four instances per class per seed):

| Mutation (detector still registered, still targeting its classes) | Effect |
|---|---|
| AP-001 window bounded to 7 days, the GL duplicate rule's default | `ap_cross_period_rekey` 0/8, exception; `ap_exact_rekey` also loses one instance, because two to five business days can be more than seven calendar days |
| AP-001 with transposition matching switched off, the rest of the battery intact | `ap_transposed_reference` 0/8, exception; the other three classes stay 8/8 |
| AP-002 window reduced to 0 days (invoice dates must match exactly) | `ap_no_reference_match` 1/8, exception |
| Battery removed entirely | all four classes 0, exception, precision "not tested" rather than 0 |

Pooled into a single "duplicate invoice" class, every one of those
regressions would have shown as a recall dip of a few points on a number
still comfortably above any floor. That is the whole argument for the split.

The second row taught something the design had not anticipated. The two
screens partition the same space — same vendor, same amount — on one shared
definition of a reference match, so with AP-001's transposition matching
off, AP-002 *still* recognises the transposition, still defers the pair as
AP-001's, and AP-001 no longer takes it: the pair falls through the crack
between them and nothing flags it. A battery whose screens disagree about
where their boundary sits leaves a gap exactly the width of the
disagreement. The partition is now asserted directly — every planted pair is
claimed by exactly one screen — as well as measured through the class.

Ground truth per plant is the two documents that constitute it — the
original and its duplicate — never the vendor's account or the amount group
they sit in (D-019, D-029). Originals are drawn only from ordinary
stochastic invoices whose (vendor, amount) is unique in the clean
population, so each plant is the only pair its manifest note describes, and
only from promptly-keyed ones, so the duplicate's own keying lag stays
inside the range the clean population already covers — a lag band that only
plants could occupy would let the calendar give away the answer (D-009's
concern, in a different field). The duplicate's clerk is drawn over all
preparers, because two clerks and one invoice is the mechanism AP dedup
exists for, and it is also why the GL's preparer-keyed R-010 cannot stand
in.

Deliberately not planted, and so deliberately not claimed: a re-key whose
*amount* was altered (both screens require equal amounts and say so), the
same invoice paid twice through two payment documents rather than recorded
twice, duplicates across vendor records that are really one vendor under two
names, and the whole accounts-receivable side of the stretch item. Each is a
different scenario needing its own plant and its own evidence, and an
unplanted class would be an unmeasured claim.

## D-035 · 2026-08-28 · The AP thresholds are measured; one screen's precision has a published ceiling
Both AP screens' parameters come from measurement on clean populations, the
way the drift floor did (D-028), not from taste.

**AP-002's invoice-date window.** Over 40 clean seeds (36,000 documents, no
plants anywhere) the screen's yield by window is flat and then falls off a
cliff: 950 flagged documents at 0 days, 950 at 3, 952 at 7, 952 at 10, 952
at 14, 954 at 21, 954 at 25 — then 1,112 at 28, 1,349 at 30 and 1,433 at 35
and beyond. The cliff is the monthly retainer: identical amount, same
vendor, invoice dates a month apart. The default of 10 days sits in the
middle of the flat region, far enough above 3 to cover a statement copy
whose invoice date shifted by a few days and 18 days clear of the first
recurring intrusion. The flat 950 is not noise to be tuned out: it is the
same-day split billing the clean population contains on purpose, and it is
the ceiling described below.

**AP-001's clean yield.** 136 flagged documents over the same 40 seeds, from
exactly two sources. 80 are the progress billing that splits a contract into
two equal instalments under one reference — a document-key duplicate on
every criterion the rule can state, and a legitimate transaction. 56 are
transposition matches on sequentially-numbered invoices that happen to carry
equal amounts: swapping a reference's last two digits moves the number by a
multiple of nine, which is inside an ordinary increment, so a vendor's own
numbering can produce a pair the criterion cannot distinguish from a
mis-key. Every one of those 56 is an *adjacent* swap, so narrowing the
criterion to adjacency — the shape of the planted error — would remove none
of them while shrinking the criterion onto the plant it is graded against.
It was left wide. Single mis-keyed digits are refused for the opposite
reason: sequential numbering makes a neighbouring reference the vendor's
next invoice, and matching it would buy recall at a false-positive cost this
population cannot bound.

**The measured card** (`python cli.py ap-card`, 20 seeds x 900 documents, two
instances of each class per seed): all four classes 40/40, recall 1.0000
(95% Wilson 0.9124-1.0000, n=40) — a *pass* against the 0.9 floor, at the
same pooled n the committed example run sizes itself for (D-020); the drift
screen next door still renders inconclusive because six instances cannot
demonstrate a floor, and this card was sized so it would not have to.
Battery precision 0.3721
(0.3404-0.4049, n=860) takes an exception against the 0.5 demo target, and
the per-rule table says why rather than averaging it away: AP-001 0.7843
(0.7349-0.8267, n=306), AP-002 0.1444 (0.1176-0.1761, n=554). False
positives run 302.7 per 10,000 clean documents (278.5-328.9 per 10k,
n=17,840), an exception against the demo ceiling.

Two honest readings go with those numbers. First, **AP-002's precision is
capped by the population, not by the tuning**: one delivery invoiced in two
same-day parts, with equal amounts and unrelated references, is the same
object as far as the criterion can see, and no threshold available to this
screen separates them. That is a finding about what amount-and-date matching
can do, reported rather than engineered around; the entries it names are
leads, and a reviewer clears split billing in seconds. Second, **precision
here is partly a statement about planted density**: at four instances per
class per seed over 10 seeds the same battery measures 0.5387 (0.4985-0.5784,
n=594) purely because the plants outnumber the fixed benign structure by
more. The false-positive rate per 10,000 clean documents barely moves
between the two runs (302.7 against 310.0), which is why it, and not
precision, is the number to compare across populations (D-025's
density-dependence lesson, restated for a subledger).
