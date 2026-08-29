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

## What it does (v1 complete — phases 0-6 of PLAN.md, plus continuous mode
and an AP subledger)

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
- **AP subledger** (`ledger/ap.py`, `rules/ap.py`) — the same discipline
  applied to payables: a deterministic subledger of vendor invoices and
  credit memos carrying the document fields a GL extract does not have
  (vendor, the vendor's own reference, the invoice date), with duplicate
  invoices planted as **four** classes rather than one — exact re-key,
  cross-period re-key, transposed reference, and re-entry under an
  unrelated reference. Two screens in their own battery: AP-001 on the
  document key at any distance, AP-002 on amount and invoice-date
  proximity where no key match exists. The split is what makes a mis-tuned
  screen visible; see DECISIONS D-033 to D-035.
- **Continuous mode** (`continuous/`) — the same discipline applied to
  monitoring: monthly batches (a batch is just a smaller ledger), a
  population-profile drift screen against a baseline period, and an
  exception aging schedule. Drift is a rule like any other (R-012, in its
  own battery) and is graded by the same report card against *planted*
  drift — composition shifts injected into known months, with the entries
  that constitute the shift as the ground truth.

## Quick start

```
python -m unittest discover -s tests -t .   # 361 tests, ~5 seconds
python cli.py example                        # regenerate examples/run-001 end to end
```

Both run in CI on every push and pull request (`.github/workflows/ci.yml`):
the suite across Python 3.10-3.13, and the committed pack regenerated and
diffed against what is in the tree. No dependencies are installed there,
which is the offline/stdlib-only claim being tested rather than repeated.

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

Other commands: `generate`, `test`, `report`, `reportcard`, `sample-size`,
`continuous`, `continuous-card`, `ap-generate`, `ap-card` (see
`python cli.py --help`).

## Continuous mode

```
python cli.py generate --plan none --drift-plan default --entries 2400 \
    --seed 511 --out runs/cont      # a ledger with planted profile drift
python cli.py continuous --ledger runs/cont --out runs/cont
python cli.py continuous-card --out runs/cont   # grade the screen
```

A drift finding needs two gates: an absolute share shift past a materiality
floor **and** non-overlapping Wilson intervals. Either alone is a bad
detector — significance without materiality just reports whatever a large n
makes detectable (the D-016 lesson again), and materiality without the
interval reports what the data cannot support. The floor's default is
calibrated against measured clean behaviour, not taste: over 40 clean seeds
it fires on 5 of 3,834 cells at ~100 entries a month and on 0 of 3,960 at
~200, and DECISIONS D-028 records the whole table including where it is
*not* silent.

Measured against planted drift (seeds 501-503, 2,400-entry ledgers): both
drift classes detected 6/6 — reported as *inconclusive*, because six
instances cannot demonstrate a 0.9 floor — with battery precision 0.66
(95% Wilson 0.63-0.68, n=1068) and 530 false positives per 10k clean
entries. That precision has a structural ceiling and the workpaper says so:
the screen concludes about a period-and-category cell, so it names the whole
cell as leads, long-standing members included. The aging schedule is
likewise careful about what it is not — with no disposition data in the lab,
it reports elapsed periods, never "open items".

## AP subledger

```
python cli.py ap-generate --out runs/ap        # 900 documents, 8 planted duplicate pairs
python cli.py test --ledger runs/ap --battery ap
python cli.py report --ledger runs/ap --battery ap --out runs/ap
python cli.py ap-card --out runs/ap            # grade the screens
```

"Duplicate invoice" is four mechanisms, not one, and they are planted and
graded as four classes because each is the one that disappears under a
different plausible mis-tuning: bound AP-001's window to seven days, the way
the GL duplicate rule bounds its own, and cross-period re-keys go to zero
while everything else stays caught; switch off transposition matching and
the transposed class goes to zero; narrow AP-002's window to exact invoice
dates and the unreferenced re-keys collapse. Pooled into one class, each of
those would have read as a few points off a recall number still above the
floor. DECISIONS D-034 has the table.

Measured by `python cli.py ap-card` (20 seeds x 900 documents, two instances
of each class per seed): all four classes 40/40 detected, recall 1.0000 (95%
Wilson 0.9124-1.0000, n=40) — a *pass* against the 0.9 floor. Battery
precision 0.3721 (0.3404-0.4049, n=860) takes an exception, and the per-rule
table says why instead of averaging it: the document-key screen runs 0.7843
(0.7349-0.8267, n=306), the amount-and-date screen 0.1444 (0.1176-0.1761,
n=554). False positives run 302.7 per 10k clean documents (278.5-328.9 per
10k, n=17,840).

That second precision figure is a finding, not a defect to tune out: one
delivery invoiced in two same-day parts, equal amounts, unrelated
references, is the same object as far as an amount-and-date criterion can
see. The clean subledger contains that split billing on purpose, along with
a monthly retainer at one repeating amount, progress billings that repeat a
reference, and credit memos that reverse an invoice — so the screens'
thresholds are calibrated against measured clean behaviour (D-035's table)
rather than taste, and their cost is printed rather than assumed away.

## Principles

Inherited from the toolkit next door, deliberately: stdlib-only Python,
everything offline and deterministic, uncertainty mandatory on every reported
rate, three outcomes (pass / exception / inconclusive), original text only
(standards referenced by ID, formulas computed rather than copied from
copyrighted tables), and flags are leads — an analytic can direct attention,
only an auditor can conclude.

*Educational/professional tooling on synthetic data; not audit software for
production use without professional supervision.*
