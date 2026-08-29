"""Synthetic accounts-payable subledger, and duplicate invoices planted in
it. The manifest IS the ground truth here exactly as it is for the
general-ledger scenarios (DECISIONS D-002): each plant records the two
entries that constitute it, and the report card grades the AP screens
against nothing else.

The subledger is not a new type. It is a `Ledger` whose entries carry a
`SourceDocument` — vendor, the vendor's own reference, the document date,
and whether the document is an invoice or a credit memo — which is what an
AP extract has and a GL extract does not (DECISIONS D-033). Every existing
rule, the profiler, the workpaper renderers and the report card therefore
operate on it unchanged, the same way a monthly batch is just a smaller
ledger (D-027).

**Four duplicate classes, not one** (DECISIONS D-034). "Duplicate invoice"
names four mechanisms with four different detectability boundaries, and each
class is the one that dies when a specific plausible mis-tuning is made:

- `ap_exact_rekey` — the same document keyed twice within days. Same
  vendor, same reference, same amount, same invoice date.
- `ap_cross_period_rekey` — the same document keyed again a period or more
  later, off a vendor statement. Identical in kind to the above; what
  differs is the distance, so a windowed duplicate screen (the GL's R-010
  looks 7 days) sees the first and misses this one entirely.
- `ap_transposed_reference` — the re-key carries a classic keying error:
  two adjacent digits of the reference swapped. An exact key match fails.
- `ap_no_reference_match` — the invoice is re-entered from a statement copy
  under a fresh internal reference. No reference match exists at all; only
  vendor, amount and invoice-date proximity remain, which is also what
  legitimate split billing looks like. This class is where the honest
  precision cost lives, and it is graded so the cost is visible.

The clean subledger is realistic rather than sterile (D-008 applied to AP):
recurring equal-amount retainers, same-day split billing, progress billings
that repeat a reference with unequal amounts, credit memos that reverse an
invoice, and invoices keyed weeks after their document date. Each of those
resembles a duplicate in one respect and is not one, so the report card's
precision and false-positive numbers mean something.

Planting draws from its own seeded stream (`"{seed}/ap-duplicates"`), so a
change to the plan never reshuffles the clean population (D-010), and ids
are issued after a shuffled within-date rank so nothing positional betrays a
plant (D-009).
"""

import random
from dataclasses import dataclass

from core.dates import (
    add_business_days,
    business_days,
    first_business_day,
    holidays_for_range,
    period_str,
)
from ledger.anomalies import Manifest, PlantedAnomaly
from ledger.generate import (
    AP_EXPENSE_ACCOUNTS,
    GENERATOR_VERSION,
    GeneratorConfig,
    VENDORS,
    _day_weights,
    _lognormal_cents,
    _months,
    default_chart,
    default_users,
    finalize_entries,
)
from ledger.model import JournalLine, Ledger, SourceDocument

AP_DUPLICATE_CLASSES = (
    "ap_exact_rekey",
    "ap_cross_period_rekey",
    "ap_transposed_reference",
    "ap_no_reference_match",
)

AP_CONTROL_ACCOUNT = "2000"

VENDOR_IDS = tuple(f"V-{i + 1:02d}" for i in range(len(VENDORS)))
# Vendors number their own documents; the formats differ, and every vendor
# numbers sequentially. Sequential numbering is why a *transposition* is a
# defensible duplicate signal and a single mis-keyed digit is not: a
# neighbouring number is an ordinary next invoice (see rules/ap.py).
REFERENCE_PREFIXES = ("INV-", "IN", "", "AP", "R-", "F")

# Benign structure, all of it documented and pinned by test (D-008 applied
# to a subledger: without look-alikes, precision would be 1.0 by
# construction and would demonstrate nothing).
RECURRING_VENDOR = "V-05"         # monthly managed-services retainer
RECURRING_CENTS = 384_517         # equal every month; cents non-zero (D-008)
SPLIT_VENDOR = "V-09"             # freight: same-day part shipments, billed apart
PROGRESS_VENDOR = "V-06"          # progress billings against one reference
CREDIT_MEMO_MONTH_STEP = 2        # a reversing credit memo every other month
LONG_LAG_SHARE = 0.06             # invoices keyed off a later vendor statement
# The clean keying lag runs continuously from 0 to this ceiling. A gap in
# it would be an artifact, not a finding: every planted re-key is keyed
# later than its own document date, so a lag range that only plants could
# occupy would let a detector recover ground truth from the calendar
# instead of from the duplication (D-009 in spirit).
LONG_LAG_BUSINESS_DAYS = (6, 70)
PROMPT_KEYING_LAG = 5             # originals are drawn from promptly-keyed invoices

# A duplicate must be able to land inside the range. Cross-period re-keys
# need the most room, and their originals are drawn from postings at least
# this many days before the end.
CROSS_PERIOD_GUARD_DAYS = 100
CROSS_PERIOD_BUSINESS_DAYS = (28, 47)   # ≈ 39 to 65 calendar days
NEAR_REKEY_BUSINESS_DAYS = (2, 6)


def default_ap_plan(multiplier: int = 1) -> dict:
    """Two instances of every duplicate class."""
    return {c: 2 * multiplier for c in AP_DUPLICATE_CLASSES}


# --- vendors and their numbering --------------------------------------------


class _VendorBook:
    """Per-vendor sequential document numbering, and the record of what has
    been issued. Planted references are checked against it: a plant that
    collided with a real document would stop being the anomaly its manifest
    note claims (the same guard the unusual-pairing scenario needs)."""

    def __init__(self, rng):
        self.ids = VENDOR_IDS
        self.name = {vid: VENDORS[i] for i, vid in enumerate(VENDOR_IDS)}
        self.prefix = {
            vid: REFERENCE_PREFIXES[i % len(REFERENCE_PREFIXES)]
            for i, vid in enumerate(VENDOR_IDS)
        }
        self.counter = {vid: rng.randrange(10_000, 90_000) for vid in VENDOR_IDS}
        self.issued = {vid: set() for vid in VENDOR_IDS}

    def next_reference(self, vendor_id: str, rng) -> str:
        # Skips a number already claimed by a planted transposition: a
        # vendor cannot issue the same reference twice, and a clean invoice
        # that happened to land on a planted one would corrupt the manifest.
        while True:
            self.counter[vendor_id] += rng.randrange(1, 10)
            ref = f"{self.prefix[vendor_id]}{self.counter[vendor_id]}"
            if ref not in self.issued[vendor_id]:
                self.issued[vendor_id].add(ref)
                return ref

    def credit_memo_reference(self, vendor_id: str, rng) -> str:
        self.counter[vendor_id] += rng.randrange(1, 10)
        ref = f"CM-{self.counter[vendor_id]}"
        self.issued[vendor_id].add(ref)
        return ref

    def is_issued(self, vendor_id: str, reference: str) -> bool:
        return reference in self.issued[vendor_id]

    def claim(self, vendor_id: str, reference: str) -> None:
        self.issued[vendor_id].add(reference)


# --- clean subledger ---------------------------------------------------------


def _invoice(
    posting_date,
    doc_date,
    vendor_id,
    reference,
    cents,
    expense_account,
    preparer_id,
    approver_id,
    description,
    doc_type="invoice",
    structural=False,
) -> dict:
    if doc_type == "invoice":
        lines = (
            JournalLine(expense_account, debit_cents=cents),
            JournalLine(AP_CONTROL_ACCOUNT, credit_cents=cents),
        )
    else:  # credit memo: the reverse of the invoice it cancels
        lines = (
            JournalLine(AP_CONTROL_ACCOUNT, debit_cents=cents),
            JournalLine(expense_account, credit_cents=cents),
        )
    return dict(
        posting_date=posting_date,
        # The effective date of a payable is the document's own date, not
        # the day a clerk keyed it. The gap between the two is ordinary
        # (invoices arrive late) and is *not* what marks a plant: clean
        # long-lag invoices are generated on purpose below.
        effective_date=doc_date,
        description=description,
        source="AP",
        preparer_id=preparer_id,
        approver_id=approver_id,
        lines=lines,
        document=SourceDocument(
            doc_type=doc_type,
            party_id=vendor_id,
            reference=reference,
            doc_date=doc_date,
        ),
        structural=structural,
    )


def _approver(cfg, rng, cents, approvers, preparer):
    """AP invoices are approved above the threshold only — the same
    convention the GL generator uses for its AP source."""
    if cents < cfg.approval_threshold_cents:
        return None
    candidates = [a for a in approvers if a != preparer] or approvers
    return rng.choice(candidates)


def _structural_invoices(cfg, rng, book, holidays, preparers, approvers) -> list:
    """Benign AP structure that resembles duplication without being it."""
    out = []
    months = [(y, m) for y, m in _months(cfg.start, cfg.end)]

    # 1. Monthly retainer: identical amount every month, own sequential
    #    references, invoice dates a month apart.
    for y, m in months:
        d = first_business_day(y, m, holidays)
        if not (cfg.start <= d <= cfg.end):
            continue
        ref = book.next_reference(RECURRING_VENDOR, rng)
        out.append(
            _invoice(
                posting_date=add_business_days(d, 2, holidays),
                doc_date=d,
                vendor_id=RECURRING_VENDOR,
                reference=ref,
                cents=RECURRING_CENTS,
                expense_account="6200",
                preparer_id=preparers[0],
                approver_id=None,
                description=f"{book.name[RECURRING_VENDOR]} managed services "
                            f"retainer {y}-{m:02d}, invoice {ref}",
                structural=True,
            )
        )

    # 2. Same-day split billing: one shipment, two invoices, equal amounts,
    #    consecutive references. This is what an amount-and-date duplicate
    #    screen cannot tell from a re-key, and it is left in deliberately.
    for y, m in months:
        d = first_business_day(y, m, holidays)
        d = add_business_days(d, 9, holidays)
        if not (cfg.start <= d <= cfg.end):
            continue
        cents = _lognormal_cents(rng, 900, 0.8, 60, 12_000)
        preparer = rng.choice(preparers)
        for half in range(2):
            ref = book.next_reference(SPLIT_VENDOR, rng)
            out.append(
                _invoice(
                    posting_date=add_business_days(d, 1, holidays),
                    doc_date=d,
                    vendor_id=SPLIT_VENDOR,
                    reference=ref,
                    cents=cents,
                    expense_account="5000",
                    preparer_id=preparer,
                    approver_id=_approver(cfg, rng, cents, approvers, preparer),
                    description=f"{book.name[SPLIT_VENDOR]} freight, part "
                                f"{half + 1} of 2, invoice {ref}",
                    structural=True,
                )
            )

    # 3. Progress billing: two documents sharing one reference, amounts
    #    unequal — except the last, which splits evenly and is therefore a
    #    document-key duplicate on every criterion but its own nature. It
    #    stays in as the residual false positive the key screen must own.
    progress_months = months[1::3][:4]
    for i, (y, m) in enumerate(progress_months):
        d = add_business_days(first_business_day(y, m, holidays), 4, holidays)
        if not (cfg.start <= d <= cfg.end):
            continue
        total = _lognormal_cents(rng, 6_000, 0.5, 2_000, 25_000)
        even = i == len(progress_months) - 1
        if even:
            total -= total % 2   # an even split has to actually be even
        first = total // 2 if even else (total * 6) // 10
        second = total - first
        ref = book.next_reference(PROGRESS_VENDOR, rng)
        preparer = rng.choice(preparers)
        for k, (cents, when) in enumerate(
            ((first, d), (second, add_business_days(d, 21, holidays)))
        ):
            if when > cfg.end:
                continue
            out.append(
                _invoice(
                    posting_date=add_business_days(when, 1, holidays),
                    doc_date=when,
                    vendor_id=PROGRESS_VENDOR,
                    reference=ref,
                    cents=cents,
                    expense_account="6900",
                    preparer_id=preparer,
                    approver_id=_approver(cfg, rng, cents, approvers, preparer),
                    description=f"{book.name[PROGRESS_VENDOR]} progress "
                                f"billing {k + 1} of 2 against invoice {ref}",
                    structural=True,
                )
            )

    # 4. Credit memo reversing an invoice: same vendor, same amount, days
    #    later, opposite direction. An amount-and-date screen that ignored
    #    direction would flag every one of these.
    for y, m in months[::CREDIT_MEMO_MONTH_STEP]:
        d = add_business_days(first_business_day(y, m, holidays), 12, holidays)
        if not (cfg.start <= d <= cfg.end):
            continue
        vendor = VENDOR_IDS[(m + 2) % len(VENDOR_IDS)]
        cents = _lognormal_cents(rng, 1_200, 0.7, 80, 15_000)
        preparer = rng.choice(preparers)
        inv_ref = book.next_reference(vendor, rng)
        out.append(
            _invoice(
                posting_date=add_business_days(d, 1, holidays),
                doc_date=d,
                vendor_id=vendor,
                reference=inv_ref,
                cents=cents,
                expense_account="6400",
                preparer_id=preparer,
                approver_id=_approver(cfg, rng, cents, approvers, preparer),
                description=f"{book.name[vendor]} invoice {inv_ref}",
                structural=True,
            )
        )
        cm_date = add_business_days(d, 6, holidays)
        if cm_date > cfg.end:
            continue
        cm_ref = book.credit_memo_reference(vendor, rng)
        out.append(
            _invoice(
                posting_date=add_business_days(cm_date, 1, holidays),
                doc_date=cm_date,
                vendor_id=vendor,
                reference=cm_ref,
                cents=cents,
                expense_account="6400",
                preparer_id=preparer,
                approver_id=None,
                description=f"{book.name[vendor]} credit memo {cm_ref} "
                            f"reversing invoice {inv_ref}",
                doc_type="credit_memo",
                structural=True,
            )
        )
    return out


def _stochastic_invoice(cfg, rng, book, holidays, days, weights, preparers, approvers):
    posting = rng.choices(days, weights=weights, k=1)[0]
    if rng.random() < LONG_LAG_SHARE:
        # Keyed off a later vendor statement. Without these, "the document
        # date is weeks behind the posting date" would identify a
        # cross-period plant on its own — an artifact, not a finding.
        lag = rng.randrange(*LONG_LAG_BUSINESS_DAYS)
    else:
        lag = rng.randrange(0, PROMPT_KEYING_LAG + 1)
    doc_date = add_business_days(posting, -lag, holidays)
    vendor = rng.choice(VENDOR_IDS)
    cents = _lognormal_cents(rng, 950, 1.0, 40, 30_000)
    expense = rng.choice(AP_EXPENSE_ACCOUNTS)
    preparer = rng.choice(preparers)
    ref = book.next_reference(vendor, rng)
    record = _invoice(
        posting_date=posting,
        doc_date=doc_date,
        vendor_id=vendor,
        reference=ref,
        cents=cents,
        expense_account=expense,
        preparer_id=preparer,
        approver_id=_approver(cfg, rng, cents, approvers, preparer),
        description=f"{book.name[vendor]} invoice {ref}",
    )
    record["keying_lag"] = lag
    return record


def generate_ap_raw(cfg: GeneratorConfig):
    """Internal: (coa, users, raw dicts with seq, holidays, vendor book).

    Exposed for the injector, which must merge planted documents before ids
    are assigned (D-009). `cfg.include_recurring` gates the benign
    structure; the GL-only switches (`include_system_batch`,
    `include_payroll`) have no meaning in a payables subledger and are
    ignored, while seed, range, entry count, day weighting and the approval
    threshold all apply.
    """
    if cfg.end < cfg.start:
        raise ValueError("end before start")
    rng = random.Random(f"{cfg.seed}/ap")
    holidays = holidays_for_range(cfg.start, cfg.end)
    days = business_days(cfg.start, cfg.end, holidays)
    if not days:
        raise ValueError("no business days in range")
    weights = _day_weights(days, cfg, holidays)
    users = default_users(cfg.n_preparers, cfg.n_approvers)
    preparers = [u.user_id for u in users if u.role == "preparer"]
    approvers = [u.user_id for u in users if u.role == "approver"]

    book = _VendorBook(rng)
    raw = (
        _structural_invoices(cfg, rng, book, holidays, preparers, approvers)
        if cfg.include_recurring
        else []
    )
    k = cfg.n_entries - len(raw)
    if k < 0:
        raise ValueError(
            f"n_entries={cfg.n_entries} below the {len(raw)} structural "
            f"documents this date range requires"
        )
    for _ in range(k):
        raw.append(
            _stochastic_invoice(
                cfg, rng, book, holidays, days, weights, preparers, approvers
            )
        )
    for i, r in enumerate(raw):
        r["seq"] = i
    return default_chart(), users, raw, holidays, book


def _meta(cfg, n_entries, extra=None) -> dict:
    meta = {
        "generator_version": GENERATOR_VERSION,
        "seed": cfg.seed,
        "fiscal_year_start": cfg.start.isoformat(),
        "fiscal_year_end": cfg.end.isoformat(),
        "approval_threshold_cents": cfg.approval_threshold_cents,
        "n_entries": n_entries,
        "subledger": "accounts_payable",
        "config": cfg.to_dict(),
    }
    if extra:
        meta.update(extra)
    return meta


def generate_ap_subledger(cfg: GeneratorConfig) -> Ledger:
    """A clean AP subledger: same config, byte-identical output."""
    coa, users, raw, _holidays, _book = generate_ap_raw(cfg)
    entries = finalize_entries(raw)
    return Ledger(coa=coa, users=users, entries=entries, meta=_meta(cfg, len(entries)))


# --- planting ----------------------------------------------------------------


@dataclass
class _APContext:
    cfg: object
    holidays: object
    raw: list
    rng: object
    book: object
    preparers: list
    approvers: list
    next_tmp: int
    available: list

    def new(self, record: dict) -> dict:
        record = dict(record)
        record["tmp"] = self.next_tmp
        self.next_tmp += 1
        self.raw.append(record)
        return record

    def take_original(self, min_days_before_end: int) -> dict:
        """Claim a clean invoice to duplicate.

        Candidates are ordinary stochastic invoices whose (vendor, amount)
        occurs exactly once in the clean population: a plant whose original
        already had an equal-amount sibling would not be the only pair its
        manifest note describes, and the ground truth would be wrong before
        any rule ran.
        """
        room = [
            r
            for r in self.available
            if (self.cfg.end - r["posting_date"]).days >= min_days_before_end
        ]
        if not room:
            raise ValueError(
                f"no clean AP invoice remains with {min_days_before_end} days "
                f"of range left to carry a duplicate"
            )
        chosen = self.rng.choice(room)
        self.available.remove(chosen)
        return chosen


def _copy_of(ctx, orig, *, posting_date, doc_date, reference, description=None):
    doc = orig["document"]
    cents = max(l.debit_cents for l in orig["lines"])
    expense = [l.account_id for l in orig["lines"] if l.debit_cents > 0][0]
    # The second keying is done by whoever picks the document up — often a
    # different clerk than the first, which is precisely why AP duplicate
    # detection keys on the document and not, as the GL's R-010 must, on
    # the preparer. The draw is over all preparers, so some plants do land
    # on the original's clerk.
    preparer = ctx.rng.choice(ctx.preparers)
    return ctx.new(
        _invoice(
            posting_date=posting_date,
            doc_date=doc_date,
            vendor_id=doc.party_id,
            reference=reference,
            cents=cents,
            expense_account=expense,
            preparer_id=preparer,
            approver_id=_approver(ctx.cfg, ctx.rng, cents, ctx.approvers, preparer),
            description=(
                description
                if description is not None
                else f"{ctx.book.name[doc.party_id]} invoice {reference}"
            ),
        )
    )


def _ap_exact_rekey(ctx, k):
    orig = ctx.take_original(30)
    doc = orig["document"]
    posting = add_business_days(
        orig["posting_date"], ctx.rng.randrange(*NEAR_REKEY_BUSINESS_DAYS), ctx.holidays
    )
    dup = _copy_of(
        ctx, orig, posting_date=posting, doc_date=doc.doc_date, reference=doc.reference
    )
    note = (
        f"Vendor {doc.party_id} invoice {doc.reference} keyed twice: the "
        f"second document carries the same reference, the same invoice date "
        f"({doc.doc_date.isoformat()}) and the same amount, posted "
        f"{posting.isoformat()} against the original's "
        f"{orig['posting_date'].isoformat()}"
    )
    return [orig["tmp"], dup["tmp"]], note


def _ap_cross_period_rekey(ctx, k):
    orig = ctx.take_original(CROSS_PERIOD_GUARD_DAYS)
    doc = orig["document"]
    posting = add_business_days(
        orig["posting_date"],
        ctx.rng.randrange(*CROSS_PERIOD_BUSINESS_DAYS),
        ctx.holidays,
    )
    dup = _copy_of(
        ctx, orig, posting_date=posting, doc_date=doc.doc_date, reference=doc.reference
    )
    note = (
        f"Vendor {doc.party_id} invoice {doc.reference} keyed a second time "
        f"{(posting - orig['posting_date']).days} days later, in period "
        f"{period_str(posting)} against the original's "
        f"{period_str(orig['posting_date'])} — same reference, same invoice "
        f"date, same amount, picked up again from a vendor statement"
    )
    return [orig["tmp"], dup["tmp"]], note


def transposition_candidates(reference: str) -> list:
    """Every reference obtainable by swapping one adjacent pair of unequal
    digits — the classic keying error. Empty when there is none to swap
    (a reference like 'INV-4444' cannot carry a transposition)."""
    out = []
    for i in range(len(reference) - 1):
        if not (reference[i].isdigit() and reference[i + 1].isdigit()):
            continue
        if reference[i] == reference[i + 1]:
            continue
        chars = list(reference)
        chars[i], chars[i + 1] = chars[i + 1], chars[i]
        out.append("".join(chars))
    return out


# Sequential vendor numbering means a transposition sometimes lands on a
# number that vendor really issued (swapping the last two digits moves the
# number by a multiple of nine, which is inside an ordinary increment). Such
# a plant would not be a duplicate of its original at all, so the builder
# tries the reference's other transpositions and then another original.
TRANSPOSITION_ATTEMPTS = 25


def _ap_transposed_reference(ctx, k):
    for _attempt in range(TRANSPOSITION_ATTEMPTS):
        orig = ctx.take_original(30)
        doc = orig["document"]
        candidates = transposition_candidates(doc.reference)
        ctx.rng.shuffle(candidates)
        reference = next(
            (c for c in candidates if not ctx.book.is_issued(doc.party_id, c)), None
        )
        if reference is not None:
            break
    else:
        raise ValueError(
            "no clean invoice remains whose reference can carry a "
            "transposition that the vendor has not already issued"
        )
    ctx.book.claim(doc.party_id, reference)
    posting = add_business_days(
        orig["posting_date"], ctx.rng.randrange(*NEAR_REKEY_BUSINESS_DAYS), ctx.holidays
    )
    dup = _copy_of(
        ctx, orig, posting_date=posting, doc_date=doc.doc_date, reference=reference
    )
    note = (
        f"Vendor {doc.party_id} invoice {doc.reference} re-keyed as "
        f"{reference} — two adjacent digits transposed — with the same "
        f"invoice date and amount, posted {posting.isoformat()}"
    )
    return [orig["tmp"], dup["tmp"]], note


def _ap_no_reference_match(ctx, k):
    orig = ctx.take_original(30)
    doc = orig["document"]
    reference = ctx.book.next_reference(doc.party_id, ctx.rng)
    doc_date = add_business_days(doc.doc_date, ctx.rng.randrange(0, 4), ctx.holidays)
    posting = add_business_days(
        orig["posting_date"], ctx.rng.randrange(*NEAR_REKEY_BUSINESS_DAYS), ctx.holidays
    )
    dup = _copy_of(
        ctx, orig, posting_date=posting, doc_date=doc_date, reference=reference
    )
    note = (
        f"Vendor {doc.party_id} invoice {doc.reference} re-entered from a "
        f"statement copy under a fresh reference {reference}: same vendor and "
        f"amount, invoice date {doc_date.isoformat()} against the original's "
        f"{doc.doc_date.isoformat()}, and no reference in common. Legitimate "
        f"split billing has the same shape"
    )
    return [orig["tmp"], dup["tmp"]], note


_BUILDERS = {
    "ap_exact_rekey": _ap_exact_rekey,
    "ap_cross_period_rekey": _ap_cross_period_rekey,
    "ap_transposed_reference": _ap_transposed_reference,
    "ap_no_reference_match": _ap_no_reference_match,
}


def _duplicable(raw) -> list:
    """Ordinary invoices eligible to be duplicated: stochastic (not part of
    the benign structure, which has its own meaning) and unique in
    (vendor, amount) across the clean population."""
    counts = {}
    for r in raw:
        doc = r["document"]
        key = (doc.party_id, max(l.debit_cents for l in r["lines"]))
        counts[key] = counts.get(key, 0) + 1
    out = []
    for r in raw:
        doc = r["document"]
        if r["structural"] or doc.doc_type != "invoice":
            continue
        if counts[(doc.party_id, max(l.debit_cents for l in r["lines"]))] != 1:
            continue
        # Originals are promptly-keyed invoices, so a duplicate's own keying
        # lag stays inside the range the clean population covers.
        if r.get("keying_lag", 0) > PROMPT_KEYING_LAG:
            continue
        out.append(r)
    out.sort(key=lambda r: r["tmp"])
    return out


def generate_ap_with_duplicates(cfg: GeneratorConfig, plan=None, anomaly_seed=None):
    """Generate an AP subledger with planted duplicate invoices.

    Returns (Ledger, Manifest). Deterministic: same (cfg, plan, seed) →
    byte-identical ledger and manifest. The parameter is named
    `anomaly_seed` to match `generate_with_anomalies`, because the report
    card calls every planting function through the same signature
    (DECISIONS D-029); it defaults to cfg.seed.

    Ground truth per plant is the two documents that constitute it — the
    original and its duplicate — never the vendor's whole account. Flagging
    the original of a duplicate pair is correct detection (D-019).
    """
    plan = dict(default_ap_plan() if plan is None else plan)
    for cls, count in sorted(plan.items()):
        if cls not in AP_DUPLICATE_CLASSES:
            raise ValueError(f"unknown AP duplicate class: {cls}")
        if not isinstance(count, int) or count < 0:
            raise ValueError(f"bad count for {cls}: {count!r}")
    aseed = cfg.seed if anomaly_seed is None else anomaly_seed

    coa, users, raw, holidays, book = generate_ap_raw(cfg)
    for i, r in enumerate(raw):
        r["tmp"] = i

    rng = random.Random(f"{aseed}/ap-duplicates")
    ctx = _APContext(
        cfg=cfg,
        holidays=holidays,
        raw=raw,
        rng=rng,
        book=book,
        preparers=sorted(u.user_id for u in users if u.role == "preparer"),
        approvers=sorted(u.user_id for u in users if u.role == "approver"),
        next_tmp=len(raw),
        available=_duplicable(raw),
    )
    if sum(plan.values()) > len(ctx.available):
        raise ValueError(
            f"{sum(plan.values())} duplicates requested but only "
            f"{len(ctx.available)} eligible clean invoices exist"
        )

    records = []
    for cls in AP_DUPLICATE_CLASSES:
        for k in range(plan.get(cls, 0)):
            tmps, note = _BUILDERS[cls](ctx, k)
            records.append((cls, tmps, note))

    for r in raw:
        r["seq"] = rng.random()
    ordered = sorted(raw, key=lambda r: (r["posting_date"], r["seq"]))
    tmp_to_id = {r["tmp"]: f"JE-{i:06d}" for i, r in enumerate(ordered, start=1)}
    entries = finalize_entries(raw)

    anomalies = tuple(
        PlantedAnomaly(
            anomaly_id=f"AP-{i:03d}",
            anomaly_class=cls,
            entry_ids=tuple(sorted(tmp_to_id[t] for t in tmps)),
            note=note,
        )
        for i, (cls, tmps, note) in enumerate(records, start=1)
    )
    manifest = Manifest(
        generator_seed=cfg.seed, anomaly_seed=aseed, plan=plan, anomalies=anomalies
    )
    meta = _meta(
        cfg,
        len(entries),
        {"duplicates": {"anomaly_seed": aseed, "plan": dict(sorted(plan.items()))}},
    )
    return Ledger(coa=coa, users=users, entries=entries, meta=meta), manifest
