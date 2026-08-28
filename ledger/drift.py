"""Planted population drift. The manifest IS the ground truth here exactly
as it is for point-in-time anomalies (DECISIONS D-002): a drift scenario
records which entry ids constitute the shift, and the report card grades the
drift screen against nothing else.

Two mechanisms, because population drift has two honest shapes:

- `preparer_concentration_drift` **reassigns** existing entries in one
  month to a single preparer. Volume is untouched; only the composition
  moves. This is the segregation-of-duties shape — one person quietly doing
  a majority of a period's postings — and reassignment (rather than
  addition) is what makes it a pure composition shift, so a volume test
  could not take credit for detecting it.
- `manual_source_surge` **adds** manual GL entries to one month, the way the
  anomaly injector adds entries: the classic "manual journal volume spiked
  this period" monitoring finding. Here volume moves too, and the mix moves
  with it.

Ground truth is the entries that *constitute* the shift — the reassigned
entries, or the added ones — never the whole drifted cell. The cell's
legitimate members are what they always were, and counting them as planted
would flatter the screen's precision by construction (DECISIONS D-029).

Like the anomaly injector, this draws from its own seeded stream
(`"{seed}/drift"`) so a change to the drift plan can never reshuffle the
clean population (D-010), and ids are issued after a shuffled within-date
rank so no positional artifact betrays the plant (D-009). Drift classes are
deliberately *not* members of `ANOMALY_CLASSES`: the point-in-time battery
has no rule designed for them, and folding them into the default plan would
book a guaranteed zero-recall class onto a card that grades a different
battery.
"""

import math
import random

from core.dates import business_days, period_str
from ledger.anomalies import Manifest, PlantedAnomaly
from ledger.generate import (
    GENERATOR_VERSION,
    GeneratorConfig,
    RECLASS_ACCOUNTS,
    finalize_entries,
    generate_raw,
)
from ledger.model import JournalLine, Ledger

DRIFT_CLASSES = (
    "preparer_concentration_drift",
    "manual_source_surge",
)

# The baseline window the plants are placed *after*. It matches
# DriftParams.baseline_periods; a plant inside the baseline would move the
# base it is measured against, so the scenario states the assumption and a
# test asserts every planted period falls outside the window.
DEFAULT_BASELINE_PERIODS = 3

# How hard each plant pushes, in absolute share points above the category's
# baseline share, with an absolute floor. Both sit clear of
# DriftParams.min_shift (0.15) so the plant is detectable by design rather
# than by luck; the report card measures whether that design holds.
DESIGNED_MARGIN = 0.22
MIN_TARGET_SHARE = 0.35

# A month too small to test is a month too small to plant in.
MIN_MONTH_ENTRIES = 40


def default_drift_plan(multiplier: int = 1) -> dict:
    """Two instances of every drift class."""
    return {c: 2 * multiplier for c in DRIFT_CLASSES}


class _DriftContext:
    def __init__(self, cfg, coa, users, holidays, raw, rng, baseline_periods):
        self.cfg = cfg
        self.coa = coa
        self.holidays = holidays
        self.raw = raw
        self.rng = rng
        self.next_tmp = len(raw)
        self.preparers = sorted(u.user_id for u in users if u.role == "preparer")
        self.approvers = sorted(u.user_id for u in users if u.role == "approver")
        self.by_month = {}
        for r in raw:
            self.by_month.setdefault(period_str(r["posting_date"]), []).append(r)
        self.months = sorted(self.by_month)
        self.baseline_months = self.months[:baseline_periods]
        self.business_days_by_month = {}
        for d in business_days(cfg.start, cfg.end, holidays):
            self.business_days_by_month.setdefault(period_str(d), []).append(d)

    def baseline_share(self, key_fn, category) -> tuple:
        """(count, total) for a category across the baseline months — the
        number the plant's note quotes and the detector will compare to."""
        total = 0
        hits = 0
        for m in self.baseline_months:
            for r in self.by_month[m]:
                total += 1
                if key_fn(r) == category:
                    hits += 1
        return hits, total

    def new(self, **fields) -> dict:
        d = dict(fields)
        d["tmp"] = self.next_tmp
        self.next_tmp += 1
        self.raw.append(d)
        return d

    def nonround_cents(self, base_dollars: int, spread_dollars: int) -> int:
        """base ± spread dollars, cents forced into 1..99 — stochastic
        amounts are never exactly .00 (D-008), so a planted drift entry
        never doubles as an accidental round-dollar plant."""
        dollars = base_dollars + self.rng.randrange(-spread_dollars, spread_dollars + 1)
        return dollars * 100 + self.rng.randrange(1, 100)

    def two_line(self, debit_acct, credit_acct, cents):
        return (
            JournalLine(debit_acct, debit_cents=cents),
            JournalLine(credit_acct, credit_cents=cents),
        )


def _entries_needed_for_share(current: int, total: int, target_share: float) -> int:
    """Smallest k of *added* entries making (current+k)/(total+k) >= target."""
    if target_share >= 1.0:
        raise ValueError("target share must be below 1")
    k = math.ceil((target_share * total - current) / (1.0 - target_share))
    return max(1, k)


def _reassignments_for_share(current: int, total: int, target_share: float) -> int:
    """Smallest k of *reassigned* entries making (current+k)/total >= target
    (the denominator does not move: nothing is added)."""
    return max(1, math.ceil(target_share * total) - current)


def _preparer_concentration_drift(ctx, month):
    rng = ctx.rng
    month_entries = ctx.by_month[month]
    total = len(month_entries)
    target = rng.choice(ctx.preparers)

    base_k, base_n = ctx.baseline_share(lambda r: r["preparer_id"], target)
    baseline_share = base_k / base_n if base_n else 0.0
    target_share = max(MIN_TARGET_SHARE, baseline_share + DESIGNED_MARGIN)

    current = sum(1 for r in month_entries if r["preparer_id"] == target)
    needed = _reassignments_for_share(current, total, target_share)

    # Reassign only human-prepared entries, and never one already approved
    # by the target: a preparer drift must not smuggle in a self-approval,
    # which is a different scenario with its own rule and its own class.
    candidates = [
        r
        for r in month_entries
        if r["preparer_id"] in ctx.preparers
        and r["preparer_id"] != target
        and r["approver_id"] != target
    ]
    candidates.sort(key=lambda r: r["tmp"])
    if len(candidates) < needed:
        raise ValueError(
            f"{month} offers {len(candidates)} reassignable entries; "
            f"{needed} are needed to lift {target} to a share of "
            f"{target_share:.2f}"
        )
    chosen = rng.sample(candidates, needed)
    chosen.sort(key=lambda r: r["tmp"])
    for r in chosen:
        r["preparer_id"] = target

    note = (
        f"In {month}, {needed} of {total} entries were reassigned to preparer "
        f"{target}: that preparer's share of the period rises from "
        f"{current}/{total} to {current + needed}/{total}, against a baseline "
        f"share of {base_k}/{base_n} over {len(ctx.baseline_months)} baseline "
        f"periods. Volume is unchanged — only the composition moves."
    )
    return [r["tmp"] for r in chosen], note


def _manual_source_surge(ctx, month):
    rng = ctx.rng
    month_entries = ctx.by_month[month]
    total = len(month_entries)

    base_k, base_n = ctx.baseline_share(lambda r: r["source"], "GL")
    baseline_share = base_k / base_n if base_n else 0.0
    target_share = max(MIN_TARGET_SHARE, baseline_share + DESIGNED_MARGIN)

    current = sum(1 for r in month_entries if r["source"] == "GL")
    needed = _entries_needed_for_share(current, total, target_share)

    days = ctx.business_days_by_month.get(month) or sorted(
        {r["posting_date"] for r in month_entries}
    )
    tmps = []
    for i in range(needed):
        # Round-robin across preparers so the surge moves the source mix
        # without dragging the preparer mix along with it.
        preparer = ctx.preparers[i % len(ctx.preparers)]
        approver = rng.choice(ctx.approvers)  # pools are disjoint (P-xx / A-xx)
        day = rng.choice(days)
        debit, credit = rng.sample(list(RECLASS_ACCOUNTS), 2)
        amount = ctx.nonround_cents(2_400, 1_500)
        e = ctx.new(
            posting_date=day,
            effective_date=day,
            description=(
                f"Manual journal {rng.randrange(1000, 9999)} — reallocation "
                f"{debit} to {credit} pending review"
            ),
            source="GL",
            preparer_id=preparer,
            approver_id=approver,
            lines=ctx.two_line(credit, debit, amount),
        )
        tmps.append(e["tmp"])

    note = (
        f"In {month}, {needed} additional manual GL entries were posted, "
        f"raising the manual-source share of the period from {current}/{total} "
        f"to {current + needed}/{total + needed}, against a baseline share of "
        f"{base_k}/{base_n} over {len(ctx.baseline_months)} baseline periods. "
        f"The added entries are spread across preparers, so the preparer mix "
        f"is left alone."
    )
    return tmps, note


_BUILDERS = {
    "preparer_concentration_drift": _preparer_concentration_drift,
    "manual_source_surge": _manual_source_surge,
}


def generate_with_drift(
    cfg: GeneratorConfig,
    plan=None,
    anomaly_seed=None,
    baseline_periods: int = DEFAULT_BASELINE_PERIODS,
):
    """Generate a ledger with planted profile drift. Returns (Ledger, Manifest).

    Deterministic: same (cfg, plan, seed, baseline_periods) → byte-identical
    ledger and manifest. The parameter is named `anomaly_seed` to match
    `generate_with_anomalies`, because the report card calls both through the
    same signature; it defaults to cfg.seed.

    Every instance gets its own month. Two plants sharing a month would each
    change the other's denominator, and neither manifest note would then
    describe the population it claims to describe.
    """
    plan = dict(default_drift_plan() if plan is None else plan)
    for cls, count in sorted(plan.items()):
        if cls not in DRIFT_CLASSES:
            raise ValueError(f"unknown drift class: {cls}")
        if not isinstance(count, int) or count < 0:
            raise ValueError(f"bad count for {cls}: {count!r}")
    dseed = cfg.seed if anomaly_seed is None else anomaly_seed

    coa, users, raw, holidays = generate_raw(cfg)
    for i, r in enumerate(raw):
        r["tmp"] = i

    rng = random.Random(f"{dseed}/drift")
    ctx = _DriftContext(cfg, coa, users, holidays, raw, rng, baseline_periods)

    eligible = [
        m
        for m in ctx.months[baseline_periods:]
        if len(ctx.by_month[m]) >= MIN_MONTH_ENTRIES
    ]
    total_instances = sum(plan.values())
    if total_instances > len(eligible):
        raise ValueError(
            f"{total_instances} drift instances requested but only "
            f"{len(eligible)} eligible months exist (periods after the "
            f"{baseline_periods}-period baseline holding at least "
            f"{MIN_MONTH_ENTRIES} entries)"
        )
    assigned = rng.sample(eligible, total_instances) if total_instances else []

    records = []
    slot = 0
    for cls in DRIFT_CLASSES:
        for _ in range(plan.get(cls, 0)):
            month = assigned[slot]
            slot += 1
            tmps, note = _BUILDERS[cls](ctx, month)
            records.append((cls, month, tmps, note))

    # Shuffled within-date rank for every entry, clean and planted alike
    # (D-009): id order must carry no injection artifact.
    for r in raw:
        r["seq"] = rng.random()
    ordered = sorted(raw, key=lambda r: (r["posting_date"], r["seq"]))
    tmp_to_id = {r["tmp"]: f"JE-{i:06d}" for i, r in enumerate(ordered, start=1)}
    entries = finalize_entries(raw)

    anomalies = tuple(
        PlantedAnomaly(
            anomaly_id=f"DR-{i:03d}",
            anomaly_class=cls,
            entry_ids=tuple(sorted(tmp_to_id[t] for t in tmps)),
            note=note,
        )
        for i, (cls, _month, tmps, note) in enumerate(records, start=1)
    )
    manifest = Manifest(
        generator_seed=cfg.seed, anomaly_seed=dseed, plan=plan, anomalies=anomalies
    )

    meta = {
        "generator_version": GENERATOR_VERSION,
        "seed": cfg.seed,
        "fiscal_year_start": cfg.start.isoformat(),
        "fiscal_year_end": cfg.end.isoformat(),
        "approval_threshold_cents": cfg.approval_threshold_cents,
        "n_entries": len(entries),
        "config": cfg.to_dict(),
        "drift": {
            "drift_seed": dseed,
            "plan": dict(sorted(plan.items())),
            "baseline_periods": baseline_periods,
            "planted_periods": sorted({m for _cls, m, _t, _n in records}),
        },
    }
    ledger = Ledger(coa=coa, users=users, entries=entries, meta=meta)
    return ledger, manifest
