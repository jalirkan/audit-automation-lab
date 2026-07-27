"""audit-automation-lab CLI.

Everything is offline, deterministic, and stdlib-only: the same command
with the same arguments produces byte-identical output. No network, no
keys, no clock reads in any artifact.

Commands:
  generate      synthetic ledger (optionally with planted anomalies)
  test          run the rule battery over a generated ledger
  report        full workpaper pack (Markdown + standalone HTML)
  reportcard    grade the battery against planted truth across seeds
  sample-size   attribute-sampling math (planning and/or evaluation)
  example       committed end-to-end run (see examples/run-001)
"""

import argparse
import json
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

from analytics.benford import benford_for_ledger
from analytics.profile import PopulationProfile
from ledger.anomalies import ANOMALY_CLASSES, Manifest, default_plan, generate_with_anomalies
from ledger.generate import GeneratorConfig, generate
from ledger.model import Ledger
from report.renderers import render_html, render_markdown
from report.workpapers import (
    build_report_card_document,
    build_sampling_workpaper,
    build_workpaper_pack,
)
from reportcard.grade import Targets, build_report_card
from rules.registry import evaluate_all
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
    if plan:
        ledger, manifest = generate_with_anomalies(
            cfg, plan, anomaly_seed=args.anomaly_seed
        )
        _write_json(out / "manifest.json", manifest.to_dict())
    else:
        ledger = generate(cfg)
    _write_json_compact(out / "ledger.json", ledger.to_dict())
    _write_text(out / "ledger.csv", ledger.entries_csv())
    planted = f", {len(plan)} anomaly classes planted" if plan else ""
    print(f"wrote {len(ledger)} entries to {out}{planted}")
    return 0


def cmd_test(args) -> int:
    ledger = _load_ledger(Path(args.ledger))
    results = evaluate_all(ledger)
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
    g.add_argument("--anomaly-seed", type=int, default=None)
    g.add_argument("--out", required=True)
    g.set_defaults(func=cmd_generate)

    t = sub.add_parser("test", help="run the rule battery over a ledger")
    t.add_argument("--ledger", required=True,
                   help="ledger.json or a directory containing it")
    t.add_argument("--out", default=None)
    t.set_defaults(func=cmd_test)

    r = sub.add_parser("report", help="write the full workpaper pack")
    r.add_argument("--ledger", required=True)
    r.add_argument("--out", required=True)
    r.set_defaults(func=cmd_report)

    c = sub.add_parser("reportcard", help="grade the battery against planted truth")
    c.add_argument("--entries", type=int, default=5000)
    c.add_argument("--seeds", default="101,102,103,104,105")
    c.add_argument("--plan", default="default")
    c.add_argument("--out", required=True)
    c.set_defaults(func=cmd_reportcard)

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
