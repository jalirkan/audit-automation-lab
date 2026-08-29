"""audit-automation-lab CLI.

Everything is offline, deterministic, and stdlib-only: the same command
with the same arguments produces byte-identical output. No network, no
keys, no clock reads in any artifact.

Commands:
  generate         synthetic ledger (optionally with planted anomalies or drift)
  test             run a rule battery over a generated ledger
  report           full workpaper pack (Markdown + standalone HTML)
  reportcard       grade the battery against planted truth across seeds
  sample-size      attribute-sampling math (planning and/or evaluation)
  continuous       monthly batches, profile drift, exception aging
  continuous-card  grade the drift screen against planted drift across seeds
  ap-generate      AP subledger with planted duplicate invoices
  ap-card          grade the AP duplicate screens against planted duplicates
  example          committed end-to-end run (see examples/run-001)
"""

import argparse
import json
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

from analytics.benford import benford_for_ledger
from analytics.profile import PopulationProfile
from continuous.aging import age_exceptions, flatten_flags
from continuous.drift import DriftParams
from continuous.periods import monthly_batches
from ledger.anomalies import ANOMALY_CLASSES, Manifest, default_plan, generate_with_anomalies
from ledger.ap import (
    AP_DUPLICATE_CLASSES,
    default_ap_plan,
    generate_ap_subledger,
    generate_ap_with_duplicates,
)
from ledger.drift import DRIFT_CLASSES, default_drift_plan, generate_with_drift
from ledger.generate import GeneratorConfig, generate
from ledger.model import Ledger
from report.renderers import render_html, render_markdown
from report.workpapers import (
    build_continuous_pack,
    build_report_card_document,
    build_sampling_workpaper,
    build_workpaper_pack,
)
from reportcard.grade import Targets, build_report_card
from rules.drift import ProfileDriftRule
from rules.registry import ap_rules, continuous_rules, default_rules, evaluate_all
from sampling.attribute import attribute_sample_size, evaluate_attribute_sample

EXAMPLE_SEED = 20260401
EXAMPLE_ENTRIES = 100_000
EXAMPLE_CARD_ENTRIES = 20_000
EXAMPLE_CARD_SEEDS = (8101, 8102, 8103, 8104, 8105)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _write_json(path: Path, obj) -> None:
    _write_text(path, json.dumps(obj, indent=2, sort_keys=True) + "\n")


def _write_json_compact(path: Path, obj) -> None:
    """Compact single-line JSON. Used for large machine-only files: with
    indent, json.dumps falls back to the pure-Python encoder, which turns a
    100k-entry ledger into minutes of serialization for no human benefit."""
    _write_text(
        path,
        json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n",
    )


def _load_ledger(path: Path) -> Ledger:
    ledger_file = path / "ledger.json" if path.is_dir() else path
    with open(ledger_file, "r", encoding="utf-8") as fh:
        return Ledger.from_dict(json.load(fh))


def _parse_plan(text: str) -> dict:
    if text == "default":
        return default_plan()
    if text == "none":
        return {}
    plan = json.loads(text)
    if not isinstance(plan, dict):
        raise ValueError("plan must be a JSON object of class -> count")
    return plan


def _parse_ap_plan(text: str) -> dict:
    if text == "default":
        return default_ap_plan()
    if text == "none":
        return {}
    plan = json.loads(text)
    if not isinstance(plan, dict):
        raise ValueError("AP plan must be a JSON object of class -> count")
    return plan


BATTERIES = {
    "default": default_rules,
    "ap": ap_rules,
    "continuous": continuous_rules,
}


def _battery(name: str) -> list:
    """Batteries are named, never mixed: a report card must grade a battery
    against the classes that battery was designed for (DECISIONS D-030,
    D-033)."""
    return BATTERIES[name]()


def _parse_drift_plan(text: str) -> dict:
    if text == "default":
        return default_drift_plan()
    if text == "none":
        return {}
    plan = json.loads(text)
    if not isinstance(plan, dict):
        raise ValueError("drift plan must be a JSON object of class -> count")
    return plan


def _battery_json(ledger, results) -> dict:
    return {
        "ledger_meta": ledger.meta,
        "results": {
            rid: {
                "applicable": res["applicable"],
                "reason": res["reason"],
                "population_size": res["population_size"],
                "n_flags": len(res["flags"]),
                "flags": [f.to_dict() for f in res["flags"]],
            }
            for rid, res in sorted(results.items())
        },
    }


def cmd_generate(args) -> int:
    cfg = GeneratorConfig(
        seed=args.seed,
        n_entries=args.entries,
        start=date.fromisoformat(args.start),
        end=date.fromisoformat(args.end),
    )
    out = Path(args.out)
    plan = _parse_plan(args.plan)
    drift_plan = _parse_drift_plan(args.drift_plan)
    if drift_plan and plan:
        # The two injectors each rebuild the same raw population; running
        # both would leave each one's manifest describing a population the
        # other had already moved. Refuse rather than silently compose.
        print(
            "--drift-plan plants population drift instead of point-in-time "
            "anomalies; pass --plan none alongside it",
            file=sys.stderr,
        )
        return 2
    if drift_plan:
        ledger, manifest = generate_with_drift(
            cfg, drift_plan, anomaly_seed=args.anomaly_seed
        )
        _write_json(out / "manifest.json", manifest.to_dict())
        plan = drift_plan
    elif plan:
        ledger, manifest = generate_with_anomalies(
            cfg, plan, anomaly_seed=args.anomaly_seed
        )
        _write_json(out / "manifest.json", manifest.to_dict())
    else:
        ledger = generate(cfg)
    _write_json_compact(out / "ledger.json", ledger.to_dict())
    _write_text(out / "ledger.csv", ledger.entries_csv())
    kind = "drift classes" if drift_plan else "anomaly classes"
    planted = f", {len(plan)} {kind} planted" if plan else ""
    print(f"wrote {len(ledger)} entries to {out}{planted}")
    return 0


def cmd_test(args) -> int:
    ledger = _load_ledger(Path(args.ledger))
    results = evaluate_all(ledger, rules=_battery(args.battery))
    out = Path(args.out) if args.out else Path(args.ledger)
    _write_json(out / "flags.json", _battery_json(ledger, results))
    total = sum(len(r["flags"]) for r in results.values())
    print(f"{total} flags across {len(results)} rules -> {out / 'flags.json'}")
    for rid, res in sorted(results.items()):
        status = "ok" if res["applicable"] else f"refused: {res['reason']}"
        print(f"  {rid}: {len(res['flags'])} flags ({status})")
    return 0


def cmd_report(args) -> int:
    ledger = _load_ledger(Path(args.ledger))
    out = Path(args.out)
    results = evaluate_all(ledger, rules=_battery(args.battery))
    benford = benford_for_ledger(ledger)
    profile = PopulationProfile.build(ledger)
    _write_json(out / "flags.json", _battery_json(ledger, results))
    pack = build_workpaper_pack(ledger, results, benford, profile)
    pack["wp-sampling"] = build_sampling_workpaper(
        size=attribute_sample_size(0.05, 0.05),
        evaluation=evaluate_attribute_sample(59, 0, 0.05, 0.05),
    )
    for name, doc in sorted(pack.items()):
        _write_text(out / "workpapers" / f"{name}.md", render_markdown(doc))
        _write_text(out / "workpapers" / f"{name}.html", render_html(doc))
    print(f"wrote {len(pack)} workpapers (md + html) to {out / 'workpapers'}")
    return 0


def cmd_reportcard(args) -> int:
    cfg = GeneratorConfig(seed=0, n_entries=args.entries)
    seeds = tuple(int(s) for s in args.seeds.split(","))
    plan = _parse_plan(args.plan)
    card = build_report_card(cfg, plan=plan or None, seeds=seeds, targets=Targets())
    out = Path(args.out)
    _write_json(out / "report-card.json", card.to_dict())
    doc = build_report_card_document(card)
    _write_text(out / "report-card.md", render_markdown(doc))
    _write_text(out / "report-card.html", render_html(doc))
    for c in card.pooled_classes:
        print(f"  {c.anomaly_class}: {c.recall.render()} -> {c.decision.outcome}")
    print(f"precision: {card.pooled_precision.render()} -> "
          f"{card.precision_decision.outcome}")
    print(f"fp rate:   {card.pooled_fp_rate.render()} -> {card.fp_decision.outcome}")
    print(f"wrote report card to {out}")
    return 0


def cmd_continuous(args) -> int:
    """Continuous mode over an existing ledger: monthly batches, profile
    drift against the baseline periods, and the aging of every exception the
    battery raises."""
    ledger = _load_ledger(Path(args.ledger))
    out = Path(args.out)
    rule = ProfileDriftRule(
        DriftParams(
            baseline_periods=args.baseline_periods,
            min_shift=args.min_shift,
        )
    )
    report = rule.analyze(ledger)
    batches = monthly_batches(ledger)

    # Aging covers the whole monitoring battery, not just drift: a
    # programme ages every lead it raises. (Grading is the opposite case —
    # there the batteries stay apart, see rules.registry.)
    results = evaluate_all(ledger, rules=default_rules() + [rule])
    schedule = age_exceptions(
        flatten_flags(results), ledger, as_of_period=args.as_of
    )

    _write_json(out / "drift.json", report.to_dict())
    _write_json(out / "aging.json", schedule.to_dict())
    _write_json(
        out / "batches.json",
        {
            "period_basis": "posting_date",
            "batches": [b.to_dict() for b in batches],
        },
    )
    pack = build_continuous_pack(ledger, rule, report, schedule)
    for name, doc in sorted(pack.items()):
        _write_text(out / "workpapers" / f"{name}.md", render_markdown(doc))
        _write_text(out / "workpapers" / f"{name}.html", render_html(doc))

    print(
        f"{len(batches)} monthly batches from {batches[0].period} to "
        f"{batches[-1].period}"
    )
    if not report.applicable:
        print(f"drift: inconclusive — {report.refusal_reason}")
    else:
        print(f"drift: baseline {', '.join(report.baseline_periods)} "
              f"(n={report.baseline_n_entries}); "
              f"{len(report.findings)} findings over "
              f"{len(report.tested_periods)} tested periods")
        for f in report.findings:
            print(f"  {f.statement}")
    print(f"aging as of {schedule.as_of_period}: "
          f"{schedule.n_exceptions} exceptions, by age "
          f"{schedule.to_dict()['by_bucket']}")
    print(f"wrote continuous-mode outputs to {out}")
    return 0


def cmd_continuous_card(args) -> int:
    """Grade the drift screen against planted drift — the same report card,
    a different battery and a different planted truth."""
    cfg = GeneratorConfig(seed=0, n_entries=args.entries)
    seeds = tuple(int(s) for s in args.seeds.split(","))
    plan = _parse_drift_plan(args.plan)
    if not plan:
        print("a non-empty drift plan is required to grade the drift screen",
              file=sys.stderr)
        return 2
    card = build_report_card(
        cfg,
        plan=plan,
        seeds=seeds,
        targets=Targets(),
        rules=continuous_rules(),
        generate=generate_with_drift,
    )
    out = Path(args.out)
    _write_json(out / "continuous-report-card.json", card.to_dict())
    doc = build_report_card_document(card)
    _write_text(out / "continuous-report-card.md", render_markdown(doc))
    _write_text(out / "continuous-report-card.html", render_html(doc))
    for c in card.pooled_classes:
        print(f"  {c.anomaly_class}: {c.recall.render()} -> {c.decision.outcome}")
    print(f"precision: {card.pooled_precision.render()} -> "
          f"{card.precision_decision.outcome}")
    print(f"fp rate:   {card.pooled_fp_rate.render()} -> {card.fp_decision.outcome}")
    print(f"wrote continuous report card to {out}")
    return 0


def cmd_ap_generate(args) -> int:
    """An accounts-payable subledger with planted duplicate invoices. It is
    a ledger like any other — the same model, the same rules interface, the
    same report card — carrying the document fields an AP extract has
    (DECISIONS D-033)."""
    cfg = GeneratorConfig(
        seed=args.seed,
        n_entries=args.entries,
        start=date.fromisoformat(args.start),
        end=date.fromisoformat(args.end),
    )
    out = Path(args.out)
    plan = _parse_ap_plan(args.plan)
    if plan:
        ledger, manifest = generate_ap_with_duplicates(
            cfg, plan, anomaly_seed=args.anomaly_seed
        )
        _write_json(out / "manifest.json", manifest.to_dict())
    else:
        # The clean subledger keeps its own canonical ordering, exactly as
        # `generate` does for a general ledger with no plan.
        ledger, manifest = generate_ap_subledger(cfg), None
    _write_json_compact(out / "ledger.json", ledger.to_dict())
    _write_text(out / "ledger.csv", ledger.entries_csv())
    planted = f", {len(manifest.anomalies)} duplicate pairs planted" if plan else ""
    print(f"wrote {len(ledger)} AP documents to {out}{planted}")
    return 0


def cmd_ap_card(args) -> int:
    """Grade the AP duplicate screens against planted duplicates — the same
    report card, a different battery and a different planted truth."""
    cfg = GeneratorConfig(seed=0, n_entries=args.entries)
    seeds = tuple(int(s) for s in args.seeds.split(","))
    plan = _parse_ap_plan(args.plan)
    if not plan:
        print("a non-empty plan is required to grade the AP screens",
              file=sys.stderr)
        return 2
    card = build_report_card(
        cfg,
        plan=plan,
        seeds=seeds,
        targets=Targets(),
        rules=ap_rules(),
        generate=generate_ap_with_duplicates,
    )
    out = Path(args.out)
    _write_json(out / "ap-report-card.json", card.to_dict())
    doc = build_report_card_document(card)
    _write_text(out / "ap-report-card.md", render_markdown(doc))
    _write_text(out / "ap-report-card.html", render_html(doc))
    for c in card.pooled_classes:
        print(f"  {c.anomaly_class}: {c.recall.render()} -> {c.decision.outcome}")
    print(f"precision: {card.pooled_precision.render()} -> "
          f"{card.precision_decision.outcome}")
    print(f"fp rate:   {card.pooled_fp_rate.render()} -> {card.fp_decision.outcome}")
    print(f"wrote AP report card to {out}")
    return 0


def cmd_sample_size(args) -> int:
    if args.deviations is None:
        r = attribute_sample_size(
            args.tolerable, args.risk,
            expected_rate=args.expected, population=args.population,
        )
        print(f"required sample size n={r.n} (allowance {r.allowance}, "
              f"achieved risk {r.achieved_risk:.4f}, {r.method})")
    else:
        if args.n is None:
            print("--n is required with --deviations", file=sys.stderr)
            return 2
        ev = evaluate_attribute_sample(
            args.n, args.deviations, args.tolerable, args.risk,
            population=args.population,
        )
        print(ev.limit.to_dict()["statement"])
        print(f"outcome: {ev.outcome} — {ev.reason}")
    return 0


def _example_pack_plan() -> dict:
    plan = default_plan(2)
    plan["unusual_pairing"] = 3  # distinct rare pairs are capped by design
    return plan


def _example_card_plan() -> dict:
    plan = {c: 8 for c in ANOMALY_CLASSES}
    plan["unusual_pairing"] = 3
    return plan


def cmd_example(args) -> int:
    """The example regenerates in independent, resumable stages so it can
    run inside constrained shells; `--stage all` does everything."""
    out = Path(args.out)
    stage = args.stage
    if stage in ("ledger", "all"):
        _example_stage_ledger(out)
    if stage in ("pack", "all"):
        _example_stage_pack(out)
    if stage in ("card", "all"):
        _example_stage_card(out)
    if stage in ("readme", "all"):
        _example_stage_readme(out)
    return 0


def _example_stage_ledger(out: Path) -> None:
    print("stage ledger: generating...", flush=True)
    cfg = GeneratorConfig(seed=EXAMPLE_SEED, n_entries=EXAMPLE_ENTRIES)
    ledger, manifest = generate_with_anomalies(cfg, _example_pack_plan())
    _write_json_compact(out / "ledger.json", ledger.to_dict())
    _write_text(out / "ledger.csv", ledger.entries_csv())
    _write_json(out / "manifest.json", manifest.to_dict())
    _write_json(
        out / "run-meta.json",
        {
            "seed": EXAMPLE_SEED,
            "n_entries": len(ledger),
            "card_entries": EXAMPLE_CARD_ENTRIES,
            "card_seeds": list(EXAMPLE_CARD_SEEDS),
        },
    )
    print(f"  {len(ledger)} entries, {len(manifest.anomalies)} planted anomalies",
          flush=True)


def _example_stage_pack(out: Path) -> None:
    print("stage pack: loading ledger...", flush=True)
    ledger = _load_ledger(out)
    print("  running battery...", flush=True)
    results = evaluate_all(ledger)
    benford = benford_for_ledger(ledger)
    profile = PopulationProfile.build(ledger)
    _write_json(out / "flags.json", _battery_json(ledger, results))
    pack = build_workpaper_pack(ledger, results, benford, profile)
    pack["wp-sampling"] = build_sampling_workpaper(
        size=attribute_sample_size(0.05, 0.05),
        evaluation=evaluate_attribute_sample(59, 0, 0.05, 0.05),
    )
    for name, doc in sorted(pack.items()):
        _write_text(out / "workpapers" / f"{name}.md", render_markdown(doc))
        _write_text(out / "workpapers" / f"{name}.html", render_html(doc))
    flagged = {f.entry_id for r in results.values() for f in r["flags"]}
    _write_json(
        out / "pack-summary.json",
        {
            "n_flags": sum(len(r["flags"]) for r in results.values()),
            "n_flagged_entries": len(flagged),
            "n_workpapers": len(pack),
        },
    )
    print(f"  {sum(len(r['flags']) for r in results.values())} flags, "
          f"{len(pack)} workpapers", flush=True)


def _example_stage_card(out: Path) -> None:
    print("stage card: grading across seeds...", flush=True)
    card = build_report_card(
        GeneratorConfig(seed=0, n_entries=EXAMPLE_CARD_ENTRIES),
        plan=_example_card_plan(),
        seeds=EXAMPLE_CARD_SEEDS,
    )
    _write_json(out / "report-card.json", card.to_dict())
    card_doc = build_report_card_document(card)
    _write_text(out / "report-card.md", render_markdown(card_doc))
    _write_text(out / "report-card.html", render_html(card_doc))
    print(f"  precision {card.pooled_precision.render()}", flush=True)


def _example_stage_readme(out: Path) -> None:
    def load(name):
        with open(out / name, "r", encoding="utf-8") as fh:
            return json.load(fh)

    meta = load("run-meta.json")
    manifest = Manifest.from_dict(load("manifest.json"))
    summary = load("pack-summary.json")
    card = load("report-card.json")

    per_class = "\n".join(
        f"- {c['anomaly_class']}: {c['n_detected']}/{c['n_planted']} detected, "
        f"recall {c['recall']['rendered']} -> {c['decision']['outcome']}"
        for c in card["pooled_classes"]
    )
    fp = card["pooled_fp_rate"]
    fp_lo, fp_hi = fp["interval"]
    text = f"""# Example run — committed end-to-end demonstration

Everything in this directory regenerates deterministically from one command
(`python cli.py example`); `ledger.json` and `ledger.csv` are gitignored
because they are large and fully determined by the seed. Nothing here is
real data (DECISIONS D-001).

## The ledger under test

- {meta["n_entries"]} journal entries, FY2025, generator seed {meta["seed"]}
- {len(manifest.anomalies)} planted anomalies across {len(manifest.by_class())} classes,
  spanning {len(manifest.all_entry_ids())} entries (`manifest.json` is the ground truth)
- battery yield: {summary["n_flags"]} flags over {summary["n_flagged_entries"]}
  distinct entries (`flags.json`; {summary["n_workpapers"]} workpapers in `workpapers/`)

## The report card (the honesty layer)

Measured against planted truth on separate ledgers
({card["config_echo"]["n_entries"]} entries x {len(card["seeds"])} seeds, richer
plan for statistical power — full tables in `report-card.md`):

{per_class}

- battery precision: {card["pooled_precision"]["rendered"]} -> {card["precision_decision"]["outcome"]}
- false positives: {card["pooled_fp_per_10k"]} per 10k clean entries
  (interval {fp_lo * 10_000:.1f}-{fp_hi * 10_000:.1f} per 10k, n={fp["n"]})

An unflattering precision outcome against the demo target is the card doing
its job: the per-rule table in `report-card.md` shows which screens buy
their recall cheaply and which sweep in review populations (period-end
selection is the dominant cost, by design of the procedure). Leads, not
conclusions, throughout.
"""
    _write_text(out / "README.md", text)
    print("stage readme: written", flush=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cli.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="generate a synthetic ledger")
    g.add_argument("--seed", type=int, default=2026)
    g.add_argument("--entries", type=int, default=5000)
    g.add_argument("--start", default="2025-01-01")
    g.add_argument("--end", default="2025-12-31")
    g.add_argument("--plan", default="default",
                   help="'default', 'none', or JSON {class: count}")
    g.add_argument("--drift-plan", default="none",
                   help=f"plant population drift instead of point-in-time "
                        f"anomalies: 'default', 'none', or JSON "
                        f"{{class: count}} over {', '.join(DRIFT_CLASSES)} "
                        f"(requires --plan none)")
    g.add_argument("--anomaly-seed", type=int, default=None)
    g.add_argument("--out", required=True)
    g.set_defaults(func=cmd_generate)

    t = sub.add_parser("test", help="run a rule battery over a ledger")
    t.add_argument("--ledger", required=True,
                   help="ledger.json or a directory containing it")
    t.add_argument("--battery", default="default", choices=sorted(BATTERIES),
                   help="which battery to run (default: the point-in-time "
                        "journal-entry rules; 'ap' tests a payables "
                        "subledger)")
    t.add_argument("--out", default=None)
    t.set_defaults(func=cmd_test)

    r = sub.add_parser("report", help="write the full workpaper pack")
    r.add_argument("--ledger", required=True)
    r.add_argument("--battery", default="default", choices=sorted(BATTERIES))
    r.add_argument("--out", required=True)
    r.set_defaults(func=cmd_report)

    c = sub.add_parser("reportcard", help="grade the battery against planted truth")
    c.add_argument("--entries", type=int, default=5000)
    c.add_argument("--seeds", default="101,102,103,104,105")
    c.add_argument("--plan", default="default")
    c.add_argument("--out", required=True)
    c.set_defaults(func=cmd_reportcard)

    cont = sub.add_parser(
        "continuous",
        help="monthly batches, profile drift vs baseline, exception aging",
    )
    cont.add_argument("--ledger", required=True,
                      help="ledger.json or a directory containing it")
    cont.add_argument("--out", required=True)
    cont.add_argument("--baseline-periods", type=int,
                      default=DriftParams().baseline_periods)
    cont.add_argument("--min-shift", type=float, default=DriftParams().min_shift,
                      help="materiality floor in absolute share points")
    cont.add_argument("--as-of", default=None,
                      help="reporting period YYYY-MM for aging "
                           "(default: the ledger's last period)")
    cont.set_defaults(func=cmd_continuous)

    cc = sub.add_parser(
        "continuous-card",
        help="grade the drift screen against planted drift across seeds",
    )
    cc.add_argument("--entries", type=int, default=2400)
    cc.add_argument("--seeds", default="501,502,503")
    cc.add_argument("--plan", default="default",
                    help="'default' or JSON {drift class: count}")
    cc.add_argument("--out", required=True)
    cc.set_defaults(func=cmd_continuous_card)

    ag = sub.add_parser(
        "ap-generate",
        help="AP subledger with planted duplicate invoices",
    )
    ag.add_argument("--seed", type=int, default=601)
    ag.add_argument("--entries", type=int, default=900)
    ag.add_argument("--start", default="2025-01-01")
    ag.add_argument("--end", default="2025-12-31")
    ag.add_argument("--plan", default="default",
                    help=f"'default', 'none', or JSON {{class: count}} over "
                         f"{', '.join(AP_DUPLICATE_CLASSES)}")
    ag.add_argument("--anomaly-seed", type=int, default=None)
    ag.add_argument("--out", required=True)
    ag.set_defaults(func=cmd_ap_generate)

    ac = sub.add_parser(
        "ap-card",
        help="grade the AP duplicate screens against planted duplicates",
    )
    ac.add_argument("--entries", type=int, default=900)
    ac.add_argument("--seeds",
                    default=",".join(str(s) for s in range(601, 621)))
    ac.add_argument("--plan", default="default",
                    help="'default' or JSON {AP duplicate class: count}")
    ac.add_argument("--out", required=True)
    ac.set_defaults(func=cmd_ap_card)

    s = sub.add_parser("sample-size", help="attribute sampling math")
    s.add_argument("--tolerable", type=float, required=True)
    s.add_argument("--risk", type=float, required=True)
    s.add_argument("--expected", type=float, default=0.0)
    s.add_argument("--population", type=int, default=None)
    s.add_argument("--n", type=int, default=None)
    s.add_argument("--deviations", type=int, default=None,
                   help="evaluate a completed sample instead of planning one")
    s.set_defaults(func=cmd_sample_size)

    e = sub.add_parser("example", help="regenerate the committed example run")
    e.add_argument("--out", default="examples/run-001")
    e.add_argument("--stage", default="all",
                   choices=("ledger", "pack", "card", "readme", "all"))
    e.set_defaults(func=cmd_example)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
