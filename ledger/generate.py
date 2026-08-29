"""Deterministic synthetic GL generator.

Everything is drawn from a single seeded `random.Random`; the same
GeneratorConfig always yields a byte-identical ledger (tested via canonical
JSON). All names — vendors, customers, users — are fictional (DECISIONS
D-001: synthetic data only, forever).

Clean-population design (DECISIONS D-008): the clean ledger is *not* sterile.
It contains documented benign structure that legitimately resembles anomaly
conditions — an exactly-round recurring rent, system batch postings that land
on weekends, a December month-end posting cluster — so that precision and
false-positive measurements in the report card are real numbers, not 1.0 by
construction. Conversely, stochastic amounts always carry non-zero cents, so
every clean-population round-dollar hit traces to a *named* benign source;
the base-rate test pins the exact counts.
"""

import math
import random
from dataclasses import dataclass, asdict
from datetime import date, timedelta

from core.dates import (
    business_days,
    first_business_day,
    holidays_for_range,
    is_business_day,
    last_n_business_days,
    month_last_day,
)
from ledger.model import Account, ChartOfAccounts, JournalEntry, JournalLine, Ledger, User

GENERATOR_VERSION = "1"

# --- fictional name banks (stable order is part of determinism) -------------

VENDORS = (
    "Northwind Office Supply",
    "Cascade Power & Light",
    "Bluepine Logistics",
    "Harborview Catering",
    "Stonebridge IT Services",
    "Juniper Field Equipment",
    "Millbrook Janitorial",
    "Foxglove Marketing Studio",
    "Granite Peak Freight",
    "Silver Birch Software",
    "Old Mill Print Co",
    "Copperline Tool & Die",
)

CUSTOMERS = (
    "Aurora Retail Group",
    "Beacon Manufacturing",
    "Copper Kettle Cafes",
    "Dune & Field Outfitters",
    "Evergreen Clinics",
    "Fairweather Hotels",
    "Gatehouse Analytics",
    "Hillcrest Schools Co-op",
    "Ironwood Builders",
    "Juno Media",
)

PREPARER_NAMES = (
    "Avery Chen",
    "Jordan Blake",
    "Priya Raman",
    "Sam Whitfield",
    "Dana Okafor",
    "Lee Marchetti",
    "Noor Haddad",
    "Casey Lund",
)

APPROVER_NAMES = ("Morgan Hale", "Riko Tanaka", "Elena Voss", "Theo Brandt")

# Sources: REV sales, CR cash receipts, AP payables, AR receivable adj,
# PAY payroll, GL manual journal, SYS automated batch.
MANUAL_SOURCES = ("REV", "CR", "AP", "AR", "GL")
SYSTEM_SOURCES = ("SYS", "PAY")

AP_EXPENSE_ACCOUNTS = ("5000", "6200", "6300", "6400", "6900")
RECLASS_ACCOUNTS = ("6200", "6300", "6350", "6400", "6900")

RENT_CENTS = 900_000          # $9,000.00 — deliberate benign round-dollar
INSURANCE_CENTS = 240_000     # $2,400.00 — benign .00, not a $1,000 multiple
DEPRECIATION_CENTS = 426_733  # $4,267.33 fixed monthly charge


@dataclass(frozen=True)
class GeneratorConfig:
    seed: int = 2026
    n_entries: int = 5000
    start: date = date(2025, 1, 1)
    end: date = date(2025, 12, 31)
    month_end_weight: float = 4.0
    december_weight: float = 1.25
    approval_threshold_cents: int = 1_000_000  # $10,000
    include_recurring: bool = True      # rent + insurance (benign round amounts)
    include_system_batch: bool = True   # depreciation + interest on calendar month-end
    include_payroll: bool = True
    n_preparers: int = 6
    n_approvers: int = 3

    def to_dict(self) -> dict:
        d = asdict(self)
        d["start"] = self.start.isoformat()
        d["end"] = self.end.isoformat()
        return d


def default_chart() -> ChartOfAccounts:
    A = Account
    return ChartOfAccounts(
        [
            A("1000", "Cash — operating", "asset", "debit"),
            A("1100", "Accounts receivable", "asset", "debit"),
            A("1200", "Inventory", "asset", "debit"),
            A("1300", "Prepaid expenses", "asset", "debit"),
            A("1500", "Equipment", "asset", "debit"),
            A("1550", "Legacy equipment — retired line", "asset", "debit",
              active=False, last_activity_before_range=date(2022, 6, 30)),
            A("1590", "Accumulated depreciation", "asset", "credit"),
            A("2000", "Accounts payable", "liability", "credit"),
            A("2100", "Accrued liabilities", "liability", "credit"),
            A("2150", "Legacy marketing accrual", "liability", "credit",
              active=False, last_activity_before_range=date(2021, 12, 31)),
            A("2200", "Payroll withholdings payable", "liability", "credit"),
            A("2500", "Notes payable", "liability", "credit"),
            A("3000", "Common equity", "equity", "credit"),
            A("3100", "Retained earnings", "equity", "credit"),
            A("4000", "Revenue — product", "revenue", "credit"),
            A("4100", "Revenue — service", "revenue", "credit"),
            A("4500", "Revenue — discontinued product line", "revenue", "credit",
              active=False, last_activity_before_range=date(2023, 3, 31)),
            A("5000", "Cost of goods sold", "expense", "debit"),
            A("6000", "Payroll expense", "expense", "debit"),
            A("6100", "Rent expense", "expense", "debit"),
            A("6200", "Utilities expense", "expense", "debit"),
            A("6300", "Travel expense", "expense", "debit"),
            A("6350", "Meals & entertainment", "expense", "debit"),
            A("6400", "Office supplies expense", "expense", "debit"),
            A("6500", "Insurance expense", "expense", "debit"),
            A("6600", "Depreciation expense", "expense", "debit"),
            A("6700", "Interest expense", "expense", "debit"),
            A("6900", "Miscellaneous expense", "expense", "debit"),
        ]
    )


def default_users(n_preparers: int, n_approvers: int) -> tuple:
    if not (1 <= n_preparers <= len(PREPARER_NAMES)):
        raise ValueError("n_preparers out of range")
    if not (1 <= n_approvers <= len(APPROVER_NAMES)):
        raise ValueError("n_approvers out of range")
    users = [
        User(f"P-{i + 1:02d}", PREPARER_NAMES[i], "preparer") for i in range(n_preparers)
    ]
    users += [
        User(f"A-{i + 1:02d}", APPROVER_NAMES[i], "approver") for i in range(n_approvers)
    ]
    users += [
        User("SYS-BATCH", "Nightly batch process", "system"),
        User("SYS-PAYROLL", "Payroll system", "system"),
    ]
    return tuple(users)


# --- amount helpers ---------------------------------------------------------


def _lognormal_cents(rng, median_dollars, sigma, lo_dollars, hi_dollars) -> int:
    """Lognormal dollars clamped to [lo, hi], cents drawn 1..99 so stochastic
    amounts are never exactly .00 (DECISIONS D-008)."""
    dollars = rng.lognormvariate(math.log(median_dollars), sigma)
    dollars = max(lo_dollars, min(hi_dollars, dollars))
    return int(dollars) * 100 + rng.randrange(1, 100)


def _two_line(debit_acct, credit_acct, cents) -> tuple:
    return (
        JournalLine(debit_acct, debit_cents=cents),
        JournalLine(credit_acct, credit_cents=cents),
    )


# --- generation -------------------------------------------------------------


def _months(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1


def _day_weights(days, cfg, holidays):
    """Base 1.0; last-2-business-days-of-month spike; December uplift."""
    month_end_days = set()
    for y, m in _months(cfg.start, cfg.end):
        lbd = None
        cur = month_last_day(y, m)
        found = []
        while len(found) < 2 and cur >= date(y, m, 1):
            if is_business_day(cur, holidays):
                found.append(cur)
            cur -= timedelta(days=1)
        month_end_days.update(found)
    weights = []
    for d in days:
        w = 1.0
        if d in month_end_days:
            w *= cfg.month_end_weight
        if d.month == 12:
            w *= cfg.december_weight
        weights.append(w)
    return weights


def _scheduled_entries(cfg, rng, holidays) -> list:
    """Recurring and system-batch entries. Dates are fixed by schedule (not
    drawn), so their calendar behaviour — e.g. depreciation landing on a
    weekend month-end — is deterministic and documented."""
    out = []
    preparers = [f"P-{i + 1:02d}" for i in range(cfg.n_preparers)]
    approvers = [f"A-{i + 1:02d}" for i in range(cfg.n_approvers)]

    if cfg.include_recurring:
        for y, m in _months(cfg.start, cfg.end):
            d = first_business_day(y, m, holidays)
            if cfg.start <= d <= cfg.end:
                out.append(
                    dict(
                        posting_date=d,
                        effective_date=d,
                        description="Monthly office rent — Lakeshore Property Mgmt",
                        source="AP",
                        preparer_id=preparers[0],
                        approver_id=None,
                        lines=_two_line("6100", "1000", RENT_CENTS),
                    )
                )
                out.append(
                    dict(
                        posting_date=d,
                        effective_date=d,
                        description="Monthly premium — Saltmarsh Mutual Insurance",
                        source="AP",
                        preparer_id=preparers[min(1, len(preparers) - 1)],
                        approver_id=None,
                        lines=_two_line("6500", "1000", INSURANCE_CENTS),
                    )
                )

    if cfg.include_system_batch:
        for y, m in _months(cfg.start, cfg.end):
            d = month_last_day(y, m)  # calendar month-end: weekends possible
            if not (cfg.start <= d <= cfg.end):
                continue
            out.append(
                dict(
                    posting_date=d,
                    effective_date=d,
                    description=f"Monthly depreciation — fixed asset register {d.year}-{d.month:02d}",
                    source="SYS",
                    preparer_id="SYS-BATCH",
                    approver_id=None,
                    lines=_two_line("6600", "1590", DEPRECIATION_CENTS),
                )
            )
            interest = 180_000 + rng.randrange(-90, 91) * 100 + rng.randrange(1, 100)
            out.append(
                dict(
                    posting_date=d,
                    effective_date=d,
                    description=f"Interest accrual — note payable {d.year}-{d.month:02d}",
                    source="SYS",
                    preparer_id="SYS-BATCH",
                    approver_id=None,
                    lines=_two_line("6700", "2100", interest),
                )
            )

    if cfg.include_payroll:
        # Biweekly from the first Friday in range; a holiday payday shifts to
        # the previous business day.
        d = cfg.start
        while d.weekday() != 4:
            d += timedelta(days=1)
        while d <= cfg.end:
            pay_date = d
            while not is_business_day(pay_date, holidays):
                pay_date -= timedelta(days=1)
            gross = 5_200_000 + rng.randrange(-2600, 2601) * 100 + rng.randrange(1, 100)
            withheld = (gross * 24) // 100
            net = gross - withheld
            out.append(
                dict(
                    posting_date=pay_date,
                    effective_date=pay_date,
                    description=f"Biweekly payroll run {pay_date.isoformat()}",
                    source="PAY",
                    preparer_id="SYS-PAYROLL",
                    approver_id=rng.choice(approvers),
                    lines=(
                        JournalLine("6000", debit_cents=gross),
                        JournalLine("1000", credit_cents=net),
                        JournalLine("2200", credit_cents=withheld),
                    ),
                )
            )
            d += timedelta(days=14)

    return out


def _stochastic_entry(cfg, rng, days, weights) -> dict:
    preparers = [f"P-{i + 1:02d}" for i in range(cfg.n_preparers)]
    approvers = [f"A-{i + 1:02d}" for i in range(cfg.n_approvers)]
    d = rng.choices(days, weights=weights, k=1)[0]

    kind = rng.choices(
        ("sales", "receipt", "ap_invoice", "ap_payment", "accrual", "reclass", "refund", "reimb"),
        weights=(22, 18, 20, 14, 8, 6, 4, 8),
        k=1,
    )[0]

    preparer = rng.choice(preparers)
    approver = None
    if kind == "sales":
        cents = _lognormal_cents(rng, 1800, 1.1, 50, 95_000)
        revenue = rng.choice(("4000", "4100"))
        customer = rng.choice(CUSTOMERS)
        desc = f"Customer invoice INV-{rng.randrange(10000, 100000)} — {customer}"
        lines, source = _two_line("1100", revenue, cents), "REV"
    elif kind == "receipt":
        cents = _lognormal_cents(rng, 1700, 1.1, 50, 95_000)
        customer = rng.choice(CUSTOMERS)
        desc = f"Receipt on account — {customer}"
        lines, source = _two_line("1000", "1100", cents), "CR"
    elif kind == "ap_invoice":
        cents = _lognormal_cents(rng, 950, 1.0, 40, 30_000)
        vendor = rng.choice(VENDORS)
        expense = rng.choice(AP_EXPENSE_ACCOUNTS)
        desc = f"{vendor} inv {rng.randrange(10000, 100000)}"
        lines, source = _two_line(expense, "2000", cents), "AP"
    elif kind == "ap_payment":
        cents = _lognormal_cents(rng, 1100, 1.0, 40, 30_000)
        vendor = rng.choice(VENDORS)
        desc = f"Payment run CHK-{rng.randrange(2000, 9999)} — {vendor}"
        lines, source = _two_line("2000", "1000", cents), "AP"
    elif kind == "accrual":
        cents = _lognormal_cents(rng, 4200, 0.9, 500, 60_000)
        expense = rng.choice(RECLASS_ACCOUNTS)
        desc = f"Month-end accrual — {expense} services rendered not yet billed"
        lines, source = _two_line(expense, "2100", cents), "GL"
    elif kind == "reclass":
        cents = _lognormal_cents(rng, 2000, 0.9, 100, 40_000)
        a, b = rng.sample(list(RECLASS_ACCOUNTS), 2)
        desc = f"Reclassification {a} to {b} — coding correction"
        lines, source = _two_line(b, a, cents), "GL"
    elif kind == "refund":
        cents = _lognormal_cents(rng, 300, 0.8, 20, 5_000)
        customer = rng.choice(CUSTOMERS)
        desc = f"Customer refund — {customer}"
        lines, source = _two_line("4000", "1000", cents), "AR"
    else:  # reimb
        cents = _lognormal_cents(rng, 240, 0.8, 20, 3_000)
        who = rng.choice(PREPARER_NAMES)
        desc = f"Expense reimbursement — {who}, travel and incidentals"
        lines, source = _two_line(rng.choice(("6300", "6350")), "1000", cents), "AP"

    amount = max(sum(l.debit_cents for l in lines), sum(l.credit_cents for l in lines))
    if source == "GL" or amount >= cfg.approval_threshold_cents:
        candidates = [a for a in approvers if a != preparer] or approvers
        approver = rng.choice(candidates)

    return dict(
        posting_date=d,
        effective_date=d,
        description=desc,
        source=source,
        preparer_id=preparer,
        approver_id=approver,
        lines=lines,
    )


def finalize_entries(raw_entries) -> tuple:
    """Sort raw entry dicts by (posting_date, seq) and assign sequential ids.

    `seq` must already be present on each dict; callers control it (the
    injector uses a shuffled rank so planted entries carry no positional
    artifact — DECISIONS D-009).

    `document` is optional: general-ledger entries record none, subledger
    entries carry a SourceDocument.
    """
    ordered = sorted(raw_entries, key=lambda r: (r["posting_date"], r["seq"]))
    entries = []
    for i, r in enumerate(ordered, start=1):
        entries.append(
            JournalEntry(
                entry_id=f"JE-{i:06d}",
                posting_date=r["posting_date"],
                effective_date=r["effective_date"],
                description=r["description"],
                source=r["source"],
                preparer_id=r["preparer_id"],
                approver_id=r["approver_id"],
                lines=r["lines"],
                document=r.get("document"),
            )
        )
    return tuple(entries)


def generate_raw(cfg: GeneratorConfig):
    """Internal: (coa, users, raw entry dicts with seq, holidays). Exposed for
    the injector, which must merge planted entries before ids are assigned."""
    if cfg.end < cfg.start:
        raise ValueError("end before start")
    rng = random.Random(f"{cfg.seed}/gl")
    holidays = holidays_for_range(cfg.start, cfg.end)
    days = business_days(cfg.start, cfg.end, holidays)
    if not days:
        raise ValueError("no business days in range")
    weights = _day_weights(days, cfg, holidays)

    raw = _scheduled_entries(cfg, rng, holidays)
    k = cfg.n_entries - len(raw)
    if k < 0:
        raise ValueError(
            f"n_entries={cfg.n_entries} below scheduled entry count {len(raw)}"
        )
    for _ in range(k):
        raw.append(_stochastic_entry(cfg, rng, days, weights))
    for i, r in enumerate(raw):
        r["seq"] = i
    return default_chart(), default_users(cfg.n_preparers, cfg.n_approvers), raw, holidays


def generate(cfg: GeneratorConfig) -> Ledger:
    """Deterministic clean ledger: same config, byte-identical output."""
    coa, users, raw, _holidays = generate_raw(cfg)
    entries = finalize_entries(raw)
    meta = {
        "generator_version": GENERATOR_VERSION,
        "seed": cfg.seed,
        "fiscal_year_start": cfg.start.isoformat(),
        "fiscal_year_end": cfg.end.isoformat(),
        "approval_threshold_cents": cfg.approval_threshold_cents,
        "n_entries": len(entries),
        "config": cfg.to_dict(),
    }
    return Ledger(coa=coa, users=users, entries=entries, meta=meta)
