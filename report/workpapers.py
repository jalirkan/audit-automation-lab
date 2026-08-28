"""Workpaper builders: per-rule workpapers, Benford workpaper, engagement
lead sheet, detection report card document, sampling workpaper, and the
continuous-mode pair (profile drift, exception aging).

Framing rules enforced here (and by tests over the rendered output):
- Counts from complete examinations are exact facts and state their
  population (n=) on the same line; intervals attach to inferential rates
  (report card, Benford digit proportions, sampling bounds) — DECISIONS
  D-023.
- Conclusions are leads. The fixed conclusion templates say what the
  procedure establishes and what it does not; renderers refuse conclusory
  language outright (report.language).
- No wall-clock timestamps: identity is fiscal year + seeds + generator
  version (D-019).
"""

from core.canonical import canonical_json
from core.stats import proportion
from ledger.model import cents_to_str
from report.document import Document, Heading, KeyValues, ListBlock, Paragraph, Table
from rules.base import REFERENCES
from sampling.attribute import BRIDGE_NOTE

MAX_EXCEPTION_ROWS = 25

LEAD_NOTE = (
    "Flags in this pack are leads for auditor follow-up. A flag directs "
    "attention; it does not, by itself, establish error or irregularity, "
    "and no automated procedure here reaches a conclusion about intent. "
    "Disposition requires auditor judgment and further procedures."
)


def _engagement_kv(ledger) -> KeyValues:
    meta = ledger.meta
    return KeyValues(
        items=(
            ("Engagement", "Synthetic ledger laboratory (all data generated; "
                           "no client data exists in this repository)"),
            ("Fiscal year", f"{meta.get('fiscal_year_start', '?')} to "
                            f"{meta.get('fiscal_year_end', '?')}"),
            ("Generator", f"version {meta.get('generator_version', '?')}, "
                          f"seed {meta.get('seed', '?')}"),
            ("Ledger size", f"{len(ledger)} journal entries"),
            ("Approval threshold",
             cents_to_str(meta.get("approval_threshold_cents", 0))),
        )
    )


def _references_block(rule) -> ListBlock:
    items = tuple(
        f"{ref} — {REFERENCES[ref]}" for ref in rule.references if ref in REFERENCES
    )
    return ListBlock(items=items or ("(no standard references cited)",))


def build_rule_workpaper(res: dict, ledger) -> Document:
    """One workpaper per rule. `res` is one entry of rules.registry.
    evaluate_all: {"rule", "applicable", "reason", "population_size",
    "flags"}."""
    rule = res["rule"]
    flags = res["flags"]
    pop = res["population_size"]
    total = len(ledger)

    blocks = [
        _engagement_kv(ledger),
        Heading("Population"),
        Paragraph(rule.population_description),
        Paragraph(
            f"Entries examined: {pop} of {total} in the ledger — a complete "
            f"examination of the defined population, not a sample; counts "
            f"below are exact (n={pop})."
        ),
        Heading("Procedure and criterion"),
        Paragraph(rule.criterion_description),
        Paragraph(f"Parameters: {canonical_json(rule.params())}"),
        Heading("References"),
        _references_block(rule),
        Heading("Results"),
    ]

    if not res["applicable"]:
        outcome = "inconclusive"
        blocks.append(
            Paragraph(
                f"Outcome: inconclusive — the procedure refused to run: "
                f"{res['reason']}. No exception count is reported, because "
                f"none would be meaningful."
            )
        )
    elif pop == 0:
        outcome = "inconclusive"
        blocks.append(
            Paragraph(
                "Outcome: inconclusive — the defined population contains no "
                "entries; the criterion was never exercised."
            )
        )
    elif flags:
        outcome = "exception"
        # A count and a denominator, no rate.
        #
        # This used to read "({share:.2%} of the population…)", and for four of
        # the eleven rules that prints "0.00%" — 4 of 100,051 is 0.004%, and two
        # decimals eat it. The figure a reader's eye lands on said the rule
        # found nothing, immediately beside a heading that says exception. Both
        # numbers were present and both correct; a true fact can still mislead
        # at the wrong size, next to the wrong neighbour.
        #
        # Reported by the assurance-suite reviewer, which quotes this sentence
        # verbatim and may not recompute it (its D-028: engine prose is carried
        # as attributed speech). Four of its records carry open challenges on it.
        # `itgc-lab` already writes the shape adopted here.
        blocks.append(
            Paragraph(
                f"Outcome: exception — {len(flags)} of {pop} entries flagged; "
                f"complete examination of the defined population, n={pop}."
            )
        )
        rows = []
        for f in flags[:MAX_EXCEPTION_ROWS]:
            e = ledger.entry(f.entry_id)
            rows.append(
                (
                    f.entry_id,
                    e.posting_date.isoformat(),
                    cents_to_str(e.amount_cents),
                    e.preparer_id,
                    f.rationale,
                )
            )
        blocks.append(
            Table(
                headers=("Entry", "Posted", "Amount", "Preparer", "Rationale"),
                rows=tuple(rows),
                caption="Exceptions with per-entry rationale",
            )
        )
        if len(flags) > MAX_EXCEPTION_ROWS:
            blocks.append(
                Paragraph(
                    f"Showing the first {MAX_EXCEPTION_ROWS} of {len(flags)} "
                    f"exceptions; the full set is in the machine-readable "
                    f"flags file accompanying this pack."
                )
            )
    else:
        outcome = "pass"
        blocks.append(
            Paragraph(
                f"Outcome: pass — no exceptions noted in a complete "
                f"examination of {pop} entries (n={pop})."
            )
        )

    blocks += [
        Heading("Limitations"),
        ListBlock(items=tuple(rule.limitations)),
        Heading("Conclusion (as lead)"),
        Paragraph(_conclusion_text(outcome, len(flags))),
        Paragraph(LEAD_NOTE),
    ]
    return Document(
        title=f"Workpaper WP-{rule.rule_id} — {rule.title}", blocks=tuple(blocks)
    )


def _conclusion_text(outcome, n_flags) -> str:
    if outcome == "inconclusive":
        return (
            "This procedure could not conclude on its criterion. That is a "
            "scope limitation, not a clean result, and it is listed as such "
            "on the lead sheet."
        )
    if outcome == "exception":
        return (
            f"{n_flags} exceptions noted. Each is a lead: an entry meeting a "
            f"criterion that historically merits a second look. The "
            f"procedure establishes that the criterion is met, and nothing "
            f"further."
        )
    return (
        "No exceptions noted. This speaks to the stated criterion over the "
        "stated population and provides no assurance beyond it."
    )


def build_benford_workpaper(benford_results: dict, ledger) -> Document:
    blocks = [_engagement_kv(ledger)]
    for name in ("first_digit", "second_digit"):
        res = benford_results[name]
        blocks.append(Heading(f"Benford {name.replace('_', ' ')} test"))
        if not res.applicable:
            blocks.append(
                Paragraph(
                    f"Outcome: inconclusive — the test refused to run: "
                    f"{res.refusal_reason}. Emitting a statistic anyway "
                    f"would manufacture false precision."
                )
            )
            continue
        blocks.append(
            KeyValues(
                items=(
                    ("Amounts tested", f"n={res.n}"),
                    ("MAD", f"{res.mad:.4f} ({res.mad_band})"),
                    ("Chi-square", f"{res.chi_square:.2f} on {res.chi_square_df} "
                                   f"degrees of freedom, p={res.p_value:.4f} "
                                   f"(n={res.n})"),
                    ("Conclusion", res.conclusion),
                )
            )
        )
        blocks.append(Paragraph(res.conclusion_reason))
        rows = []
        for d in sorted(res.counts):
            m = res.digit_measurements[d]
            rows.append(
                (
                    str(d),
                    str(res.counts[d]),
                    f"{res.expected_proportions[d]:.4f}",
                    m.render(),
                )
            )
        blocks.append(
            Table(
                headers=("Digit", "Observed count", "Expected proportion",
                         "Observed proportion (with interval)"),
                rows=tuple(rows),
            )
        )
    blocks += [
        Heading("Conclusion (as lead)"),
        Paragraph(
            "Digit-conformity results are population-level leads: a "
            "departure directs attention to the strata that drive it and is "
            "not an assertion about any individual entry."
        ),
        Paragraph(LEAD_NOTE),
    ]
    return Document(title="Workpaper WP-BENFORD — Digit conformity", blocks=tuple(blocks))


def build_lead_sheet(ledger, results: dict, benford_results: dict, profile) -> Document:
    all_flagged = set()
    rows = []
    inconclusive_rows = []
    for rid in sorted(results):
        res = results[rid]
        rule = res["rule"]
        if not res["applicable"]:
            outcome = "inconclusive"
            yield_cell = f"refused: {res['reason']}"
            inconclusive_rows.append(rid)
        elif res["flags"]:
            outcome = "exception"
            k, pop = len(res["flags"]), res["population_size"]
            # Count and denominator, no rate — the same reason as the workpaper
            # sentence above. This cell printed "4/100051 (0.00%)" for four of
            # the eleven rules, on the page a reader meets first.
            yield_cell = f"{k}/{pop}"
            all_flagged |= {f.entry_id for f in res["flags"]}
        else:
            outcome = "pass"
            yield_cell = f"0/{res['population_size']}"
        rows.append((rid, rule.title, str(res["population_size"]), yield_cell, outcome))

    benford_rows = []
    for name in ("first_digit", "second_digit"):
        res = benford_results[name]
        benford_rows.append(
            (
                name.replace("_", " "),
                f"n={res.n}",
                "-" if res.mad is None else f"{res.mad:.4f}",
                res.mad_band or "-",
                res.conclusion,
            )
        )

    src = ", ".join(f"{k}: {v}" for k, v in profile.by_source.items())
    blocks = [
        _engagement_kv(ledger),
        Heading("Population overview"),
        KeyValues(
            items=(
                ("Journal entries", str(profile.n_entries)),
                ("Journal lines", str(profile.n_lines)),
                ("Posting dates", f"{profile.date_min} to {profile.date_max}"),
                ("By source", src),
                ("Entries requiring approval", str(profile.n_requiring_approval)),
                ("Approvals missing", str(profile.n_missing_approval)),
            )
        ),
        Heading("Journal-entry tests"),
        Table(
            headers=("Rule", "Title", "Population", "Exceptions", "Outcome"),
            rows=tuple(rows),
            caption="Complete examinations; exception counts are exact",
        ),
        Heading("Digit conformity"),
        Table(
            headers=("Test", "Amounts", "MAD", "Band", "Conclusion"),
            rows=tuple(benford_rows),
        ),
        Heading("Lead summary"),
        Paragraph(
            f"Distinct entries flagged by at least one rule: "
            f"{len(all_flagged)} of {len(ledger)} "
            f"({len(all_flagged) / len(ledger):.2%} of the ledger, n={len(ledger)})."
        ),
        Paragraph(LEAD_NOTE),
    ]
    if inconclusive_rows:
        blocks.append(
            Paragraph(
                "Procedures that could not conclude (scope limitations, "
                "listed separately from findings): " + ", ".join(inconclusive_rows)
            )
        )
    return Document(title="Engagement lead sheet — journal-entry testing", blocks=tuple(blocks))


def build_report_card_document(card) -> Document:
    d = card.to_dict()
    class_rows = []
    for c in card.pooled_classes:
        class_rows.append(
            (
                c.anomaly_class,
                str(c.n_planted),
                str(c.n_detected),
                c.recall.render(),
                c.decision.outcome,
                f"{c.recall_min:.2f}-{c.recall_max:.2f}",
            )
        )

    # Pooled per-rule precision across runs.
    per_rule = {}
    for run in card.runs:
        for rg in run.rule_grades:
            agg = per_rule.setdefault(rg.rule_id, [0, 0])
            agg[0] += rg.n_flags
            agg[1] += rg.n_true
    rule_rows = []
    for rid in sorted(per_rule):
        flags_n, true_n = per_rule[rid]
        m = proportion(f"precision[{rid}]", true_n, flags_n,
                       direction="higher_is_better")
        rule_rows.append(
            (rid, str(flags_n), str(true_n), str(flags_n - true_n),
             m.render() if flags_n else "no flags produced")
        )

    run_rows = []
    for run in card.runs:
        run_rows.append(
            (
                str(run.seed),
                str(run.n_entries),
                str(run.n_planted_instances),
                str(run.n_flagged_entries),
                run.precision.render(),
                f"{run.fp_rate.value * 10_000:.1f}/10k (n={run.fp_rate.n})",
            )
        )

    missed_rows = []
    for run in card.runs:
        for c in run.class_grades:
            for aid in c.missed:
                missed_rows.append((str(run.seed), c.anomaly_class, aid))

    fp = card.pooled_fp_rate
    lo, hi = fp.interval
    blocks = [
        Paragraph(
            "The lab grades itself before it grades a ledger: every rule ran "
            "against synthetic ledgers whose anomalies are known by "
            "construction (the injector manifest is the ground truth), and "
            "the rates below are measured against that truth. A detection "
            "capability without such a report card is a claim without "
            "evidence."
        ),
        Heading("Definitions"),
        KeyValues(items=tuple(sorted(d["definitions"].items()))),
        Heading("Targets"),
        KeyValues(
            items=(
                ("Recall floor (per class)", str(card.targets.recall_target)),
                ("Precision floor", str(card.targets.precision_target)),
                ("False-positive ceiling", str(card.targets.fp_rate_target)),
                ("Minimum pooled sample for a pass", str(card.targets.min_sample)),
                ("Caveat", "targets are engagement parameters chosen for this "
                           "lab, not professional standards"),
            )
        ),
        Heading("Recall by planted class (pooled across seeds)"),
        Table(
            headers=("Class", "Planted", "Detected", "Recall (Wilson)",
                     "Outcome", "Per-seed range"),
            rows=tuple(class_rows),
            caption=f"Seeds: {', '.join(str(s) for s in card.seeds)}",
        ),
        Heading("Battery precision and false-positive load"),
        KeyValues(
            items=(
                ("Precision (entry level)", card.pooled_precision.render()),
                ("Precision outcome", card.precision_decision.outcome
                 + " — " + card.precision_decision.reason),
                ("False-positive rate", fp.render()),
                ("False positives per 10,000 clean entries",
                 f"{fp.value * 10_000:.1f} (interval {lo * 10_000:.1f}-"
                 f"{hi * 10_000:.1f} per 10k, n={fp.n})"),
                ("FP outcome", card.fp_decision.outcome
                 + " — " + card.fp_decision.reason),
            )
        ),
        Heading("Per-rule precision (pooled)"),
        Table(
            headers=("Rule", "Flags", "Planted hits", "Clean hits",
                     "Precision (Wilson)"),
            rows=tuple(rule_rows),
            caption="Clean hits are the cost side of each rule: legitimate "
                    "entries swept in as leads",
        ),
        Heading("Per-run summary"),
        Table(
            headers=("Seed", "Entries", "Planted instances", "Flagged",
                     "Precision", "FP load"),
            rows=tuple(run_rows),
        ),
    ]
    if missed_rows:
        blocks += [
            Heading("Missed instances"),
            Table(headers=("Seed", "Class", "Anomaly"), rows=tuple(missed_rows)),
        ]
    blocks += [
        Heading("Reading this card"),
        Paragraph(
            "Outcomes are decided by comparing the Wilson interval to the "
            "target, never the point estimate: a class caught 6 times out of "
            "6 planted renders inconclusive against a 0.9 floor, because six "
            "instances cannot demonstrate it. Inconclusive is reported, "
            "never rounded up to pass."
        ),
        Paragraph(
            "Precision is deliberately not 1.0: the clean population "
            "contains benign structure (recurring round-dollar rent, system "
            "batches posting on weekend month-ends, a December close "
            "cluster) precisely so the false-positive cost of each rule is "
            "measured rather than assumed away."
        ),
    ]
    return Document(title="Detection report card", blocks=tuple(blocks))


def build_drift_workpaper(rule, report, ledger) -> Document:
    """Continuous-mode workpaper: profile drift against the baseline period.

    Findings that name no entries (share decreases) and periods that could
    not be tested both appear here. A monitoring workpaper that showed only
    the entry-bearing findings would report a quieter population than the
    one that was examined.
    """
    blocks = [
        _engagement_kv(ledger),
        Heading("Population"),
        Paragraph(rule.population_description),
        Paragraph(
            f"Batching basis: posting month. Baseline periods: "
            f"{', '.join(report.baseline_periods) or '(none)'} "
            f"(n={report.baseline_n_entries} entries). Periods tested "
            f"against that baseline: "
            f"{', '.join(report.tested_periods) or '(none)'}."
        ),
        Heading("Procedure and criterion"),
        Paragraph(rule.criterion_description),
        Paragraph(f"Parameters: {canonical_json(rule.params())}"),
        Heading("References"),
        _references_block(rule),
        Heading("Results"),
    ]

    if not report.applicable:
        outcome = "inconclusive"
        blocks.append(
            Paragraph(
                f"Outcome: inconclusive — the procedure refused to run: "
                f"{report.refusal_reason}. No drift finding is reported, "
                f"because none would be meaningful."
            )
        )
    elif report.findings:
        outcome = "exception"
        n_leads = len({eid for f in report.findings for eid in f.entry_ids})
        blocks.append(
            Paragraph(
                f"Outcome: exception — {len(report.findings)} composition "
                f"shifts identified across {len(report.tested_periods)} tested "
                f"periods, naming {n_leads} entries as leads."
            )
        )
        blocks.append(
            Table(
                headers=("Period", "Dimension", "Category", "Direction",
                         "Shift (share points)", "Baseline share",
                         "Period share", "Entries in cell"),
                rows=tuple(
                    (
                        f.period,
                        f.dimension.replace("by_", ""),
                        f.category,
                        f.direction,
                        f"{f.shift:+.3f}",
                        f.baseline_share.render(),
                        f.period_share.render(),
                        str(len(f.entry_ids)),
                    )
                    for f in report.findings
                ),
                caption="Each row is a period-and-category cell, not an "
                        "entry; the cell's entries are the leads",
            )
        )
    else:
        outcome = "pass"
        blocks.append(
            Paragraph(
                f"Outcome: pass — no composition shift met the criterion in "
                f"{len(report.tested_periods)} tested periods measured against "
                f"a baseline of n={report.baseline_n_entries} entries."
            )
        )

    if report.untested:
        blocks += [
            Heading("Periods not tested (scope limitations)"),
            Table(
                headers=("Period", "Entries", "Reason"),
                rows=tuple(
                    (u.period, str(u.n_entries), u.reason) for u in report.untested
                ),
            ),
        ]

    blocks += [
        Heading("Limitations"),
        ListBlock(items=tuple(rule.limitations)),
        Heading("Conclusion (as lead)"),
        Paragraph(_conclusion_text(outcome, len(report.findings))),
        Paragraph(LEAD_NOTE),
    ]
    return Document(
        title=f"Workpaper WP-{rule.rule_id} — {rule.title}", blocks=tuple(blocks)
    )


def build_aging_workpaper(schedule, ledger) -> Document:
    """Continuous-mode workpaper: how long each lead has been outstanding."""
    bucket_rows = tuple(
        (b, str(schedule.by_bucket.get(b, 0))) for b in schedule.buckets
    )
    rule_rows = tuple(
        (rid,) + tuple(str(counts.get(b, 0)) for b in schedule.buckets)
        + (str(sum(counts.values())),)
        for rid, counts in sorted(schedule.by_rule.items())
    )
    oldest_rows = tuple(
        (a.rule_id, a.entry_id, a.first_seen_period, str(a.age_periods))
        for a in schedule.oldest()
    )

    blocks = [
        _engagement_kv(ledger),
        Heading("Basis"),
        Paragraph(
            f"Exceptions are filed under the monthly batch in which they "
            f"first appeared and aged in whole periods against the reporting "
            f"period {schedule.as_of_period}. Counts are exact: "
            f"{schedule.n_exceptions} exceptions aged, "
            f"{schedule.n_not_yet_posted} not yet visible as of that period."
        ),
        Paragraph(
            "This schedule is not an open-items list. No disposition record "
            "exists in this lab — no clearing dates, no reviewer sign-off — "
            "so every exception raised is aged, including any a reviewer "
            "would already have cleared. A programme with follow-up records "
            "would age only the undispositioned ones, and the difference "
            "matters for anything read off the older buckets."
        ),
        Heading("Aging profile"),
        Table(
            headers=("Age (periods)", "Exceptions"),
            rows=bucket_rows,
            caption=f"Oldest bucket is open-ended; maximum observed age "
                    f"{schedule.max_age_periods} periods",
        ),
    ]
    if rule_rows:
        blocks += [
            Heading("Aging by rule"),
            Table(
                headers=("Rule",) + schedule.buckets + ("Total",),
                rows=rule_rows,
            ),
        ]
    if oldest_rows:
        blocks += [
            Heading("Oldest outstanding leads"),
            Table(
                headers=("Rule", "Entry", "First seen", "Age (periods)"),
                rows=oldest_rows,
                caption=f"Showing up to {len(oldest_rows)} of "
                        f"{schedule.n_exceptions} aged exceptions",
            ),
        ]
    blocks += [
        Heading("Conclusion (as lead)"),
        Paragraph(
            "An aged exception is a lead that has been available for review "
            "for the stated number of periods. Age is evidence about the "
            "monitoring process, not about the entry: an old lead is not a "
            "worse exception, it is an unworked one."
        ),
        Paragraph(LEAD_NOTE),
    ]
    return Document(
        title="Workpaper WP-AGING — Exception aging", blocks=tuple(blocks)
    )


def build_continuous_pack(ledger, drift_rule, drift_report, schedule) -> dict:
    """name -> Document for a continuous-mode run."""
    return {
        "wp-drift": build_drift_workpaper(drift_rule, drift_report, ledger),
        "wp-aging": build_aging_workpaper(schedule, ledger),
    }


def build_sampling_workpaper(size=None, evaluation=None) -> Document:
    blocks = [
        Heading("Bridge from full-population analytics"),
        Paragraph(BRIDGE_NOTE),
    ]
    if size is not None:
        blocks += [
            Heading("Sample size (attribute sampling)"),
            KeyValues(
                items=(
                    ("Tolerable deviation rate", f"{size.tolerable_rate:.4f}"),
                    ("Expected deviation rate", f"{size.expected_rate:.4f}"),
                    ("Risk of overreliance", f"{size.risk:.4f}"),
                    ("Population", "large (binomial)" if size.population is None
                     else str(size.population)),
                    ("Required sample size", f"n={size.n}"),
                    ("Planned deviation allowance", str(size.allowance)),
                    ("Achieved risk at n", f"{size.achieved_risk:.4f}"),
                    ("Method", f"{size.method}, computed from the defining "
                               f"inequality (no table lookup)"),
                )
            ),
        ]
    if evaluation is not None:
        lim = evaluation.limit
        blocks += [
            Heading("Sample evaluation"),
            KeyValues(
                items=(
                    ("Sample", f"{lim.deviations} deviations in n={lim.n}"),
                    ("Observed rate", f"{lim.sample_rate:.4f}"),
                    ("Upper deviation limit", lim.to_dict()["statement"]),
                    ("Tolerable rate", f"{evaluation.tolerable_rate:.4f}"),
                    ("Outcome", evaluation.outcome),
                    ("Basis", evaluation.reason),
                )
            ),
        ]
    blocks.append(Paragraph(LEAD_NOTE))
    return Document(title="Workpaper WP-SAMPLING — Attribute sampling", blocks=tuple(blocks))


def build_workpaper_pack(ledger, results, benford_results, profile) -> dict:
    """name -> Document for the whole engagement pack (report card and
    sampling docs are built separately by their own inputs)."""
    pack = {"lead-sheet": build_lead_sheet(ledger, results, benford_results, profile)}
    for rid in sorted(results):
        pack[f"wp-{rid.lower()}"] = build_rule_workpaper(results[rid], ledger)
    pack["wp-benford"] = build_benford_workpaper(benford_results, ledger)
    return pack
