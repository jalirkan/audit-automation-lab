"""Grade the rule battery against planted ground truth.

Definitions (these fix the meaning of every reported number):

- Planted entry ids: the union of entry ids across the manifest's anomalies.
  For pair scenarios (duplicates) this includes the original entry — it is
  part of the anomaly, and flagging it is correct detection.
- An anomaly instance is DETECTED when at least one of its entry ids is
  flagged by at least one rule. "Designed" recall restricts that to rules
  whose `targets` include the instance's class; "any-rule" recall does not.
- Per-class recall: detected instances / planted instances of that class.
- Precision (entry level): flagged entries that are planted / all flagged
  entries. A flagged clean entry is a false positive *as a lead*, whatever
  its rationale.
- False-positive rate: flagged clean entries / clean entries (clean =
  entries not referenced by any anomaly). Displayed per 10,000 entries;
  the underlying Measurement is the raw proportion.

Every rate is a Measurement with a Wilson interval and its n (DECISIONS
D-004/D-015); outcomes are decided interval-vs-target, so small planted
counts yield *inconclusive*, not a hollow pass — 20/20 caught cannot
demonstrate a 0.9 recall floor, and the card says so.

No wall-clock timestamps appear anywhere: report cards are part of the
byte-identical determinism contract (D-007). Identity is carried by seeds
and config echoes instead.
"""

from dataclasses import dataclass, replace

from analytics.benford import benford_for_ledger
from core.stats import Decision, Measurement, decide, proportion
from ledger.anomalies import default_plan, generate_with_anomalies
from rules.registry import default_rules, evaluate_all

PER_10K = 10_000


@dataclass(frozen=True)
class Targets:
    """Engagement parameters, not standards: the thresholds the card grades
    against. Defaults are demo choices and render with that caveat."""

    recall_target: float = 0.9
    precision_target: float = 0.5
    fp_rate_target: float = 0.02
    min_sample: int = 20

    def to_dict(self) -> dict:
        return {
            "recall_target": self.recall_target,
            "precision_target": self.precision_target,
            "fp_rate_target": self.fp_rate_target,
            "min_sample": self.min_sample,
        }


@dataclass(frozen=True)
class RuleGrade:
    rule_id: str
    n_flags: int
    n_true: int
    n_false: int
    precision: Measurement

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "n_flags": self.n_flags,
            "n_true": self.n_true,
            "n_false": self.n_false,
            "precision": self.precision.to_dict(),
        }


@dataclass(frozen=True)
class ClassGrade:
    anomaly_class: str
    n_planted: int
    n_detected_any: int
    n_detected_designed: int
    recall_any: Measurement
    recall_designed: Measurement
    missed: tuple
    caught_by: dict  # anomaly_id -> sorted rule ids that hit it

    def to_dict(self) -> dict:
        return {
            "anomaly_class": self.anomaly_class,
            "n_planted": self.n_planted,
            "n_detected_any": self.n_detected_any,
            "n_detected_designed": self.n_detected_designed,
            "recall_any": self.recall_any.to_dict(),
            "recall_designed": self.recall_designed.to_dict(),
            "missed": list(self.missed),
            "caught_by": {k: list(v) for k, v in sorted(self.caught_by.items())},
        }


@dataclass(frozen=True)
class RunGrade:
    seed: int
    anomaly_seed: int
    n_entries: int
    n_planted_instances: int
    n_planted_entries: int
    n_flagged_entries: int
    class_grades: tuple
    rule_grades: tuple
    precision: Measurement
    fp_rate: Measurement
    benford_notes: dict

    def to_dict(self) -> dict:
        return {
            "seed": self.seed,
            "anomaly_seed": self.anomaly_seed,
            "n_entries": self.n_entries,
            "n_planted_instances": self.n_planted_instances,
            "n_planted_entries": self.n_planted_entries,
            "n_flagged_entries": self.n_flagged_entries,
            "class_grades": [c.to_dict() for c in self.class_grades],
            "rule_grades": [r.to_dict() for r in self.rule_grades],
            "precision": self.precision.to_dict(),
            "fp_rate": self.fp_rate.to_dict(),
            "fp_per_10k": round(self.fp_rate.value * PER_10K, 2),
            "benford_notes": self.benford_notes,
        }


def grade_run(ledger, manifest, rules=None) -> RunGrade:
    """Grade one battery run on one planted ledger."""
    results = evaluate_all(ledger, rules=default_rules() if rules is None else rules)

    flags_by_rule = {rid: {f.entry_id for f in res["flags"]} for rid, res in results.items()}
    all_flagged = set()
    for s in flags_by_rule.values():
        all_flagged |= s

    planted_ids = manifest.all_entry_ids()
    n_entries = len(ledger)
    n_clean = n_entries - len(planted_ids)

    # Per-class grades.
    class_grades = []
    for cls in sorted({a.anomaly_class for a in manifest.anomalies}):
        instances = [a for a in manifest.anomalies if a.anomaly_class == cls]
        detected_any = 0
        detected_designed = 0
        missed = []
        caught_by = {}
        for a in instances:
            ids = set(a.entry_ids)
            hitting = sorted(
                rid for rid, flagged in flags_by_rule.items() if flagged & ids
            )
            designed = [
                rid
                for rid in hitting
                if cls in results[rid]["rule"].targets
            ]
            if hitting:
                detected_any += 1
                caught_by[a.anomaly_id] = hitting
            else:
                missed.append(a.anomaly_id)
            if designed:
                detected_designed += 1
        n = len(instances)
        class_grades.append(
            ClassGrade(
                anomaly_class=cls,
                n_planted=n,
                n_detected_any=detected_any,
                n_detected_designed=detected_designed,
                recall_any=proportion(
                    f"recall[{cls}] (any rule)", detected_any, n,
                    direction="higher_is_better",
                ),
                recall_designed=proportion(
                    f"recall[{cls}] (designed rules)", detected_designed, n,
                    direction="higher_is_better",
                ),
                missed=tuple(missed),
                caught_by=caught_by,
            )
        )

    # Per-rule precision.
    rule_grades = []
    for rid in sorted(flags_by_rule):
        flagged = flags_by_rule[rid]
        n_true = len(flagged & planted_ids)
        rule_grades.append(
            RuleGrade(
                rule_id=rid,
                n_flags=len(flagged),
                n_true=n_true,
                n_false=len(flagged) - n_true,
                precision=proportion(
                    f"precision[{rid}]", n_true, len(flagged),
                    direction="higher_is_better",
                ),
            )
        )

    n_true_total = len(all_flagged & planted_ids)
    n_false_total = len(all_flagged) - n_true_total

    benford = benford_for_ledger(ledger)
    benford_notes = {
        name: {
            "applicable": res.applicable,
            "conclusion": res.conclusion,
            "mad": None if res.mad is None else round(res.mad, 6),
        }
        for name, res in sorted(benford.items())
    }

    return RunGrade(
        seed=ledger.meta.get("seed"),
        # From the manifest, not the ledger metadata: the manifest is the
        # ground truth (D-002) and every planting path records its stream
        # seed there, whatever shape its ledger meta takes.
        anomaly_seed=manifest.anomaly_seed,
        n_entries=n_entries,
        n_planted_instances=len(manifest.anomalies),
        n_planted_entries=len(planted_ids),
        n_flagged_entries=len(all_flagged),
        class_grades=tuple(class_grades),
        rule_grades=tuple(rule_grades),
        precision=proportion(
            "precision (battery, entry level)", n_true_total, len(all_flagged),
            direction="higher_is_better",
        ),
        fp_rate=proportion(
            "false-positive rate (clean entries)", n_false_total, n_clean,
            direction="lower_is_better",
        ),
        benford_notes=benford_notes,
    )


@dataclass(frozen=True)
class PooledClass:
    anomaly_class: str
    n_planted: int
    n_detected: int
    recall: Measurement
    decision: Decision
    per_seed: dict     # seed -> "k/n"
    recall_min: float
    recall_max: float
    # The rules whose `targets` name this class — the design link, as designed,
    # not which rules happened to catch instances this run. That distinction is
    # why this is not derived from class_grades[].caught_by.
    designed_rules: tuple = ()

    def to_dict(self) -> dict:
        return {
            "anomaly_class": self.anomaly_class,
            "designed_rules": list(self.designed_rules),
            "n_planted": self.n_planted,
            "n_detected": self.n_detected,
            "recall": self.recall.to_dict(),
            "decision": self.decision.to_dict(),
            "per_seed": {str(k): v for k, v in sorted(self.per_seed.items())},
            "recall_min": round(self.recall_min, 6),
            "recall_max": round(self.recall_max, 6),
        }


@dataclass(frozen=True)
class ReportCard:
    config_echo: dict
    plan: dict
    seeds: tuple
    targets: Targets
    runs: tuple
    pooled_classes: tuple
    pooled_precision: Measurement
    precision_decision: Decision
    pooled_fp_rate: Measurement
    fp_decision: Decision

    def to_dict(self) -> dict:
        return {
            "definitions": {
                "detected": "an instance counts as detected when any rule "
                            "flags any of its entry ids",
                "precision": "flagged entries that are planted / all flagged "
                             "entries",
                "fp_rate": "flagged clean entries / clean entries (also "
                           "shown per 10,000)",
                "note": "targets are engagement parameters, not standards; "
                        "outcomes are decided interval-vs-target, so small "
                        "planted counts yield inconclusive, not a pass",
            },
            "config_echo": self.config_echo,
            "plan": dict(sorted(self.plan.items())),
            "seeds": list(self.seeds),
            "targets": self.targets.to_dict(),
            "runs": [r.to_dict() for r in self.runs],
            "pooled_classes": [c.to_dict() for c in self.pooled_classes],
            "pooled_precision": self.pooled_precision.to_dict(),
            "precision_decision": self.precision_decision.to_dict(),
            "pooled_fp_rate": self.pooled_fp_rate.to_dict(),
            "pooled_fp_per_10k": round(self.pooled_fp_rate.value * PER_10K, 2),
            "fp_decision": self.fp_decision.to_dict(),
        }


def build_report_card(
    base_config,
    plan=None,
    seeds=(101, 102, 103, 104, 105),
    targets: Targets = Targets(),
    rules=None,
    generate=generate_with_anomalies,
) -> ReportCard:
    """Run a battery across several seeded ledgers and pool the grades.

    Pooling across seeds is what gives recall a sample size worth deciding
    on: with the default plan, one seed plants too few instances per class
    for any interval to clear a 0.9 floor, and the card would say
    inconclusive — correctly.

    `generate` is the planting function, `(config, plan) -> (ledger,
    manifest)`. Continuous mode passes `ledger.drift.generate_with_drift`
    with a drift plan and the continuous battery: grading a new detection
    capability means running *this* card over *its* planted truth, not
    writing a second scorer with its own definitions (DECISIONS D-029).
    """
    if not seeds:
        raise ValueError("at least one seed required")
    if len(set(seeds)) != len(seeds):
        raise ValueError("seeds must be distinct")
    if plan is None and generate is not generate_with_anomalies:
        raise ValueError(
            "a plan is required when grading with an alternate generator: "
            "the point-in-time default plan names classes it cannot plant"
        )
    plan = dict(default_plan() if plan is None else plan)

    # Materialize once: the same battery grades every seed (a caller-passed
    # iterator would otherwise be exhausted on the first), and it is the
    # design-time source for pooled_classes[].designed_rules below.
    battery = default_rules() if rules is None else list(rules)

    runs = []
    for seed in seeds:
        cfg = replace(base_config, seed=seed)
        ledger, manifest = generate(cfg, plan)
        runs.append((seed, grade_run(ledger, manifest, rules=battery)))

    all_classes = sorted({c.anomaly_class for _, r in runs for c in r.class_grades})
    pooled_classes = []
    for cls in all_classes:
        n_planted = 0
        n_detected = 0
        per_seed = {}
        points = []
        for seed, run in runs:
            for c in run.class_grades:
                if c.anomaly_class == cls:
                    n_planted += c.n_planted
                    n_detected += c.n_detected_any
                    per_seed[seed] = f"{c.n_detected_any}/{c.n_planted}"
                    points.append(c.recall_any.value)
        recall = proportion(
            f"pooled recall[{cls}]", n_detected, n_planted,
            direction="higher_is_better",
        )
        pooled_classes.append(
            PooledClass(
                anomaly_class=cls,
                n_planted=n_planted,
                n_detected=n_detected,
                recall=recall,
                decision=decide(recall, targets.recall_target,
                                min_sample=targets.min_sample),
                per_seed=per_seed,
                recall_min=min(points),
                recall_max=max(points),
                designed_rules=tuple(
                    sorted(r.rule_id for r in battery if cls in r.targets)
                ),
            )
        )

    true_total = sum(r.precision.numerator for _, r in runs)
    flagged_total = sum(r.precision.n for _, r in runs)
    false_total = sum(r.fp_rate.numerator for _, r in runs)
    clean_total = sum(r.fp_rate.n for _, r in runs)

    pooled_precision = proportion(
        "pooled precision (battery, entry level)", true_total, flagged_total,
        direction="higher_is_better",
    )
    pooled_fp = proportion(
        "pooled false-positive rate (clean entries)", false_total, clean_total,
        direction="lower_is_better",
    )

    return ReportCard(
        config_echo=base_config.to_dict(),
        plan=plan,
        seeds=tuple(seeds),
        targets=targets,
        runs=tuple(r for _, r in runs),
        pooled_classes=tuple(pooled_classes),
        pooled_precision=pooled_precision,
        precision_decision=decide(pooled_precision, targets.precision_target,
                                  min_sample=targets.min_sample),
        pooled_fp_rate=pooled_fp,
        fp_decision=decide(pooled_fp, targets.fp_rate_target,
                           min_sample=targets.min_sample),
    )
