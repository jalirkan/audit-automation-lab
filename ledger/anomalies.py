"""Planted-anomaly injector. The manifest IS the ground truth (DECISIONS
D-002): every scenario records exactly which entry ids constitute the
anomaly, and the detection report card grades rules against nothing else.

Injection happens *before* entry ids are assigned: clean and planted raw
entries are merged, every entry receives a shuffled within-date rank, and
ids are issued in (posting_date, rank) order. A detector therefore cannot
learn ground truth from id gaps, suffixes, or intra-day position
(DECISIONS D-009).

The injector draws from its own seeded stream (`"{seed}/anomalies"`), so a
change to the anomaly plan never reshuffles the clean population
(DECISIONS D-010).
"""

import random
from dataclasses import dataclass

from core.dates import add_business_days, business_days, is_weekend, last_n_business_days
from ledger.generate import (
    AP_EXPENSE_ACCOUNTS,
    GeneratorConfig,
    VENDORS,
    finalize_entries,
    generate_raw,
    GENERATOR_VERSION,
)
from ledger.model import JournalLine, Ledger

ANOMALY_CLASSES = (
    "late_round_dollar",
    "post_close_entry",
    "self_approval",
    "duplicate_pair",
    "near_duplicate",
    "threshold_shaving",
    "dormant_reactivation",
    "unbalanced_entry",
    "missing_description",
    "weekend_manual",
    "unusual_pairing",
)

# Deliberately-rare account pairings for the unusual_pairing scenario. Each
# instance uses a *different* pair (cycled by index): if two plants shared a
# pair, that pair would occur twice in the population and a "pair appears
# exactly once" criterion could never see either. Plan counts above
# len(UNUSUAL_PAIRS) are rejected for the same reason.
UNUSUAL_PAIRS = (
    ("6700", "4000"),  # DR interest expense / CR product revenue
    ("6600", "4100"),  # DR depreciation expense / CR service revenue
    ("1300", "4900"),  # DR prepaid expenses / CR other income
)


@dataclass(frozen=True)
class PlantedAnomaly:
    anomaly_id: str
    anomaly_class: str
    entry_ids: tuple
    note: str

    def to_dict(self) -> dict:
        return {
            "anomaly_id": self.anomaly_id,
            "anomaly_class": self.anomaly_class,
            "entry_ids": list(self.entry_ids),
            "note": self.note,
        }

    @staticmethod
    def from_dict(d: dict) -> "PlantedAnomaly":
        return PlantedAnomaly(
            d["anomaly_id"], d["anomaly_class"], tuple(d["entry_ids"]), d["note"]
        )


@dataclass
class Manifest:
    generator_seed: int
    anomaly_seed: int
    plan: dict
    anomalies: tuple

    def all_entry_ids(self) -> frozenset:
        out = set()
        for a in self.anomalies:
            out |= set(a.entry_ids)
        return frozenset(out)

    def by_class(self) -> dict:
        out = {}
        for a in self.anomalies:
            out.setdefault(a.anomaly_class, []).append(a)
        return out

    def to_dict(self) -> dict:
        return {
            "generator_seed": self.generator_seed,
            "anomaly_seed": self.anomaly_seed,
            "plan": dict(sorted(self.plan.items())),
            "n_anomalies": len(self.anomalies),
            "n_planted_entries": len(self.all_entry_ids()),
            "anomalies": [a.to_dict() for a in self.anomalies],
        }

    @staticmethod
    def from_dict(d: dict) -> "Manifest":
        return Manifest(
            generator_seed=d["generator_seed"],
            anomaly_seed=d["anomaly_seed"],
            plan=dict(d["plan"]),
            anomalies=tuple(PlantedAnomaly.from_dict(a) for a in d["anomalies"]),
        )


def default_plan(multiplier: int = 1) -> dict:
    """Two instances of every class (threshold_shaving counts series)."""
    return {c: 2 * multiplier for c in ANOMALY_CLASSES}


class _Context:
    def __init__(self, cfg, coa, users, holidays, raw, rng):
        self.cfg = cfg
        self.coa = coa
        self.holidays = holidays
        self.raw = raw
        self.rng = rng
        self.next_tmp = len(raw)
        self.preparers = sorted(u.user_id for u in users if u.role == "preparer")
        self.approvers = sorted(u.user_id for u in users if u.role == "approver")
        self.bdays = business_days(cfg.start, cfg.end, holidays)
        self.fy_end = cfg.end
        self.threshold = cfg.approval_threshold_cents
        # Clean-population debit/credit account pairs, for the unusual_pairing
        # collision guard.
        self.clean_pairs = set()
        for r in raw:
            debits = [l.account_id for l in r["lines"] if l.debit_cents > 0]
            credits = [l.account_id for l in r["lines"] if l.credit_cents > 0]
            for da in debits:
                for ca in credits:
                    self.clean_pairs.add((da, ca))
        # Pre-drawn duplicate/near-duplicate originals are filled by inject().
        self.dup_originals = []

    def new(self, **fields) -> dict:
        d = dict(fields)
        d["tmp"] = self.next_tmp
        self.next_tmp += 1
        self.raw.append(d)
        return d

    def nonround_cents(self, base_cents: int, spread_dollars: int) -> int:
        """base ± spread dollars, cents forced into 1..99 (never .00)."""
        dollars = base_cents // 100 + self.rng.randrange(-spread_dollars, spread_dollars + 1)
        return dollars * 100 + self.rng.randrange(1, 100)

    def two_line(self, debit_acct, credit_acct, cents):
        return (
            JournalLine(debit_acct, debit_cents=cents),
            JournalLine(credit_acct, credit_cents=cents),
        )


def _late_round_dollar(ctx, k):
    rng = ctx.rng
    amount = rng.choice((1_500_000, 2_500_000, 4_000_000))
    (day,) = last_n_business_days(ctx.fy_end, 1, ctx.holidays)
    preparer = rng.choice(ctx.preparers)
    e = ctx.new(
        posting_date=day,
        effective_date=day,
        description="Year-end adjustment per management review",
        source="GL",
        preparer_id=preparer,
        approver_id=rng.choice(ctx.approvers),
        lines=ctx.two_line("6900", "2100", amount),
    )
    note = (
        f"Manual entry of exactly {amount // 100} dollars posted on the final "
        f"business day of the fiscal year by {preparer}"
    )
    return [e["tmp"]], note


def _post_close_entry(ctx, k):
    rng = ctx.rng
    posting = add_business_days(ctx.fy_end, rng.randrange(2, 6), ctx.holidays)
    amount = ctx.nonround_cents(1_800_000, 900)
    e = ctx.new(
        posting_date=posting,
        effective_date=ctx.fy_end,
        description="Post-close revenue true-up — Q4 recognition",
        source="GL",
        preparer_id=rng.choice(ctx.preparers),
        approver_id=rng.choice(ctx.approvers),
        lines=ctx.two_line("1100", "4000", amount),
    )
    note = (
        f"Revenue entry posted {posting.isoformat()}, after fiscal year end, "
        f"effective back into the closed period"
    )
    return [e["tmp"]], note


def _self_approval(ctx, k):
    rng = ctx.rng
    preparer = rng.choice(ctx.preparers)
    amount = ctx.threshold + ctx.nonround_cents(280_000, 150)
    e = ctx.new(
        posting_date=rng.choice(ctx.bdays),
        effective_date=None,  # set below
        description="Vendor settlement — expedited processing",
        source="GL",
        preparer_id=preparer,
        approver_id=preparer,
        lines=ctx.two_line("6900", "2000", amount),
    )
    e["effective_date"] = e["posting_date"]
    note = f"Entry above the approval threshold prepared and approved by the same user {preparer}"
    return [e["tmp"]], note


def _pick_dup_original(ctx):
    if not ctx.dup_originals:
        raise ValueError("not enough AP invoice entries to plant duplicates")
    return ctx.dup_originals.pop(0)


def _duplicate_pair(ctx, k):
    orig = _pick_dup_original(ctx)
    posting = add_business_days(orig["posting_date"], 2, ctx.holidays)
    e = ctx.new(
        posting_date=posting,
        effective_date=posting,
        description=orig["description"],
        source=orig["source"],
        preparer_id=orig["preparer_id"],
        approver_id=orig["approver_id"],
        lines=orig["lines"],
    )
    note = (
        f"Exact duplicate (same vendor invoice reference, amount, accounts, "
        f"preparer) posted two business days after the original"
    )
    return [orig["tmp"], e["tmp"]], note


def _near_duplicate(ctx, k):
    orig = _pick_dup_original(ctx)
    amount = max(l.debit_cents for l in orig["lines"])
    bumped = amount + max(100, (amount * 7) // 1000)  # ≈ +0.7%
    debit_acct = [l.account_id for l in orig["lines"] if l.debit_cents > 0][0]
    credit_acct = [l.account_id for l in orig["lines"] if l.credit_cents > 0][0]
    posting = add_business_days(orig["posting_date"], 3, ctx.holidays)
    e = ctx.new(
        posting_date=posting,
        effective_date=posting,
        description=orig["description"] + " (resubmitted)",
        source=orig["source"],
        preparer_id=orig["preparer_id"],
        approver_id=orig["approver_id"],
        lines=ctx.two_line(debit_acct, credit_acct, bumped),
    )
    note = (
        f"Near-duplicate of the original vendor invoice: same accounts and "
        f"preparer, amount shifted about 0.7 percent, three business days later"
    )
    return [orig["tmp"], e["tmp"]], note


def _threshold_shaving(ctx, k):
    rng = ctx.rng
    preparer = rng.choice(ctx.preparers)
    vendor = rng.choice(VENDORS)
    expense = rng.choice(("6300", "6400", "6900"))
    start_idx = rng.randrange(0, max(1, len(ctx.bdays) - 12))
    day = ctx.bdays[start_idx]
    tmps = []
    for _ in range(3):
        amount = ctx.threshold - (rng.randrange(25, 600) * 100 + rng.randrange(1, 100))
        e = ctx.new(
            posting_date=day,
            effective_date=day,
            description=f"{vendor} inv {rng.randrange(10000, 100000)}",
            source="AP",
            preparer_id=preparer,
            approver_id=None,
            lines=ctx.two_line(expense, "2000", amount),
        )
        tmps.append(e["tmp"])
        day = add_business_days(day, rng.randrange(1, 4), ctx.holidays)
    note = (
        f"Series of three {vendor} invoices by {preparer} within a few business "
        f"days, each just below the approval threshold — none individually "
        f"required approval"
    )
    return tmps, note


def _dormant_reactivation(ctx, k):
    rng = ctx.rng
    acct_id = rng.choice(ctx.coa.inactive_ids())
    acct = ctx.coa.get(acct_id)
    amount = ctx.nonround_cents(612_000, 300)
    if acct.type == "revenue":
        lines = ctx.two_line("1100", acct_id, amount)
    elif acct.type == "liability":
        lines = ctx.two_line(acct_id, "1000", amount)
    else:  # asset
        lines = ctx.two_line(acct_id, "1000", amount)
    day = rng.choice(ctx.bdays)
    e = ctx.new(
        posting_date=day,
        effective_date=day,
        description="Legacy account activity — see supporting memo",
        source="GL",
        preparer_id=rng.choice(ctx.preparers),
        approver_id=rng.choice(ctx.approvers),
        lines=lines,
    )
    note = f"Posting to dormant account {acct_id} ({acct.name}), inactive since {acct.last_activity_before_range}"
    return [e["tmp"]], note


def _unbalanced_entry(ctx, k):
    rng = ctx.rng
    debit = ctx.nonround_cents(521_000, 200)
    short = rng.randrange(50, 500) * 100
    day = rng.choice(ctx.bdays)
    e = ctx.new(
        posting_date=day,
        effective_date=day,
        description="Manual import adjustment — batch 7 of 7",
        source="GL",
        preparer_id=rng.choice(ctx.preparers),
        approver_id=rng.choice(ctx.approvers),
        lines=(
            JournalLine("6900", debit_cents=debit),
            JournalLine("1000", credit_cents=debit - short),
        ),
    )
    note = f"Debits exceed credits by {short // 100} dollars — entry does not balance"
    return [e["tmp"]], note


def _missing_description(ctx, k):
    rng = ctx.rng
    amount = ctx.nonround_cents(341_000, 250)
    day = rng.choice(ctx.bdays)
    e = ctx.new(
        posting_date=day,
        effective_date=day,
        description="",
        source="GL",
        preparer_id=rng.choice(ctx.preparers),
        approver_id=rng.choice(ctx.approvers),
        lines=ctx.two_line("6400", "2000", amount),
    )
    note = "Manual entry recorded with no description"
    return [e["tmp"]], note


def _weekend_manual(ctx, k):
    rng = ctx.rng
    weekend_days = [
        d for d in _all_days(ctx.cfg.start, ctx.cfg.end) if is_weekend(d)
    ]
    day = rng.choice(weekend_days)
    amount = ctx.nonround_cents(287_000, 180)
    preparer = rng.choice(ctx.preparers)
    e = ctx.new(
        posting_date=day,
        effective_date=day,
        description="Correction entry processed over weekend",
        source="GL",
        preparer_id=preparer,
        approver_id=rng.choice(ctx.approvers),
        lines=ctx.two_line("6900", "2100", amount),
    )
    note = f"Manual entry posted on a {day.strftime('%A')} by human user {preparer}"
    return [e["tmp"]], note


def _unusual_pairing(ctx, k):
    rng = ctx.rng
    pair = UNUSUAL_PAIRS[k % len(UNUSUAL_PAIRS)]
    if pair in ctx.clean_pairs:
        raise RuntimeError(
            f"unusual_pairing pair {pair} collides with a clean-population "
            f"pair; the planted pair must be absent from the clean ledger"
        )
    amount = ctx.nonround_cents(784_000, 220)
    day = rng.choice(ctx.bdays)
    e = ctx.new(
        posting_date=day,
        effective_date=day,
        description="Reclassification adjustment — account recoding",
        source="GL",
        preparer_id=rng.choice(ctx.preparers),
        approver_id=rng.choice(ctx.approvers),
        lines=ctx.two_line(pair[0], pair[1], amount),
    )
    note = (
        f"Debit {pair[0]} / credit {pair[1]} — an account pairing that "
        f"appears nowhere else in the population"
    )
    return [e["tmp"]], note


def _all_days(start, end):
    from datetime import timedelta

    out = []
    cur = start
    while cur <= end:
        out.append(cur)
        cur += timedelta(days=1)
    return out


_BUILDERS = {
    "late_round_dollar": _late_round_dollar,
    "post_close_entry": _post_close_entry,
    "self_approval": _self_approval,
    "duplicate_pair": _duplicate_pair,
    "near_duplicate": _near_duplicate,
    "threshold_shaving": _threshold_shaving,
    "dormant_reactivation": _dormant_reactivation,
    "unbalanced_entry": _unbalanced_entry,
    "missing_description": _missing_description,
    "weekend_manual": _weekend_manual,
    "unusual_pairing": _unusual_pairing,
}


def _ap_invoice_candidates(raw, cfg):
    """Clean AP vendor invoices suitable as duplicate originals: two lines,
    credit to AP control (2000), debit to an expense account, dated early
    enough that a copy a few days later stays inside the range."""
    cutoff_guard = 20
    out = []
    for r in raw:
        if r["source"] != "AP" or len(r["lines"]) != 2:
            continue
        debits = [l for l in r["lines"] if l.debit_cents > 0]
        credits = [l for l in r["lines"] if l.credit_cents > 0]
        if len(debits) != 1 or len(credits) != 1:
            continue
        if credits[0].account_id != "2000":
            continue
        if debits[0].account_id not in AP_EXPENSE_ACCOUNTS:
            continue
        if (cfg.end - r["posting_date"]).days < cutoff_guard:
            continue
        out.append(r)
    return out


def generate_with_anomalies(cfg: GeneratorConfig, plan=None, anomaly_seed=None):
    """Generate a ledger with planted anomalies. Returns (Ledger, Manifest).

    Deterministic: same (cfg, plan, anomaly_seed) → byte-identical ledger and
    manifest. anomaly_seed defaults to cfg.seed.
    """
    plan = dict(default_plan() if plan is None else plan)
    for cls, count in sorted(plan.items()):
        if cls not in ANOMALY_CLASSES:
            raise ValueError(f"unknown anomaly class: {cls}")
        if not isinstance(count, int) or count < 0:
            raise ValueError(f"bad count for {cls}: {count!r}")
    if plan.get("unusual_pairing", 0) > len(UNUSUAL_PAIRS):
        raise ValueError(
            f"unusual_pairing count above {len(UNUSUAL_PAIRS)} would repeat a "
            f"pair and defeat the rarity the scenario plants"
        )
    aseed = cfg.seed if anomaly_seed is None else anomaly_seed

    coa, users, raw, holidays = generate_raw(cfg)
    for i, r in enumerate(raw):
        r["tmp"] = i

    rng = random.Random(f"{aseed}/anomalies")
    ctx = _Context(cfg, coa, users, holidays, raw, rng)

    needed_originals = plan.get("duplicate_pair", 0) + plan.get("near_duplicate", 0)
    if needed_originals:
        candidates = _ap_invoice_candidates(raw[: len(raw)], cfg)
        candidates.sort(key=lambda r: r["tmp"])
        if len(candidates) < needed_originals:
            raise ValueError(
                f"only {len(candidates)} AP invoice entries available; "
                f"{needed_originals} duplicate originals requested"
            )
        ctx.dup_originals = rng.sample(candidates, needed_originals)

    records = []
    for cls in ANOMALY_CLASSES:
        for k in range(plan.get(cls, 0)):
            tmps, note = _BUILDERS[cls](ctx, k)
            records.append((cls, tmps, note))

    # Shuffled within-date rank for every entry (clean and planted alike), so
    # id order carries no injection artifact.
    for r in raw:
        r["seq"] = rng.random()
    ordered = sorted(raw, key=lambda r: (r["posting_date"], r["seq"]))
    tmp_to_id = {r["tmp"]: f"JE-{i:06d}" for i, r in enumerate(ordered, start=1)}
    entries = finalize_entries(raw)

    anomalies = tuple(
        PlantedAnomaly(
            anomaly_id=f"AN-{i:03d}",
            anomaly_class=cls,
            entry_ids=tuple(tmp_to_id[t] for t in tmps),
            note=note,
        )
        for i, (cls, tmps, note) in enumerate(records, start=1)
    )
    manifest = Manifest(
        generator_seed=cfg.seed, anomaly_seed=aseed, plan=plan, anomalies=anomalies
    )

    meta = {
        "generator_version": GENERATOR_VERSION,
        "seed": cfg.seed,
        "fiscal_year_start": cfg.start.isoformat(),
        "fiscal_year_end": cfg.end.isoformat(),
        "approval_threshold_cents": cfg.approval_threshold_cents,
        "n_entries": len(entries),
        "config": cfg.to_dict(),
        "anomalies": {"anomaly_seed": aseed, "plan": dict(sorted(plan.items()))},
    }
    ledger = Ledger(coa=coa, users=users, entries=entries, meta=meta)
    return ledger, manifest
