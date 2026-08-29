"""The accounts-payable battery: two duplicate-invoice screens over a
subledger extract.

These are rules in the same sense the general-ledger eleven are — declared
population, stated criterion, per-entry rationale, refusal when their
preconditions fail — but they read fields the GL does not have. An AP
extract carries the vendor, the vendor's own document reference and the
document date as *fields*; the GL carries the same facts, when it carries
them at all, inside free text, which is why the GL's near-duplicate screen
is lexical and says so (D-013). Keying on the fields is what makes AP-001 a
tight test rather than a string-similarity heuristic (DECISIONS D-033).

The two rules partition the same space — same vendor, same amount — by
whether a reference match exists:

- **AP-001** takes the pairs whose references match, exactly or through a
  digit transposition, and takes them *at any distance*. A vendor does not
  issue one reference twice, so how far apart the two keyings landed is not
  evidence against duplication; the GL's R-010 bounds its window because
  identical *line structure* legitimately repeats, and that reasoning does
  not carry over to a document key (DECISIONS D-034).
- **AP-002** takes the pairs where no reference match exists at all, and
  bounds them by invoice-date proximity because nothing else remains. Its
  precision is capped by how much legitimate split billing the population
  contains; the report card prints the number rather than the rule being
  tuned until it looks better (DECISIONS D-035).

Neither rule matches a *single* mis-keyed digit. Vendors number
sequentially, so a reference one digit away from another is routinely the
vendor's next invoice; a transposition is not a number a sequence produces.
That boundary is a deliberate refusal to buy recall with an unbounded
false-positive cost, and the limitation is printed in the workpaper.

The battery is separate from `default_rules()` for the same reason the
continuous battery is (D-030): it tests a different population with fields
that population alone has, and grading it in a mixed battery would credit
its recall to screens that read none of those fields.
"""

from ledger.model import cents_to_str
from rules.base import Flag, Rule, sort_flags

# Measured, not chosen for looks (DECISIONS D-035): the clean-population
# calibration table over 40 seeds sits in that entry.
DEFAULT_INVOICE_DATE_WINDOW = 10


def is_transposition(a: str, b: str) -> bool:
    """True when b is a with exactly two digits swapped.

    Any two positions, not only adjacent ones: the planted keying error is
    the classic adjacent swap, so a criterion restricted to adjacency would
    be a criterion shaped around the plant it is graded on.
    """
    if a == b or len(a) != len(b):
        return False
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    if len(diff) != 2:
        return False
    i, j = diff
    if not (a[i].isdigit() and a[j].isdigit()):
        return False
    return a[i] == b[j] and a[j] == b[i]


def reference_match(a: str, b: str, allow_transposed: bool = True) -> str:
    """The basis on which two vendor references name the same document:
    "exact", "transposed", or the empty string for no match.

    Both rules call this one function. The boundary between them is exactly
    this predicate, so if they disagreed about where it sits, pairs would
    fall through the gap and nothing would flag them — which is what
    happens, measurably, when one of them is detuned (DECISIONS D-034).
    """
    if a == b:
        return "exact"
    if allow_transposed and is_transposition(a, b):
        return "transposed"
    return ""


def _invoices(ledger, include_credit_memos=False):
    out = []
    for e in ledger.entries:
        doc = e.document
        if doc is None:
            continue
        if doc.doc_type != "invoice" and not include_credit_memos:
            continue
        out.append(e)
    return out


def _group(entries):
    """Vendor and amount are the two facts every duplicate mechanism here
    shares; grouping on them keeps the pair comparison local."""
    groups = {}
    for e in entries:
        groups.setdefault((e.document.party_id, e.amount_cents), []).append(e)
    return groups


class _APRule(Rule):
    """Shared plumbing: the population is the subledger's invoice documents,
    and a ledger that carries no document fields is refused rather than
    tested (DECISIONS D-011)."""

    include_credit_memos = False

    def population(self, ledger):
        return _invoices(ledger, self.include_credit_memos)

    def applicable(self, ledger):
        if not any(e.document is not None for e in ledger.entries):
            return False, (
                "no entry in this population carries subledger document "
                "fields (vendor, reference, document date); this procedure "
                "tests an accounts-payable extract, not a general ledger"
            )
        if not self.population(ledger):
            return False, "the population contains no vendor invoice documents"
        return True, ""


class DuplicateInvoiceReferenceRule(_APRule):
    rule_id = "AP-001"
    title = "Duplicate vendor invoices on the document key"
    targets = (
        "ap_exact_rekey",
        "ap_cross_period_rekey",
        "ap_transposed_reference",
    )
    references = ("AU-C 240",)
    population_description = (
        "Vendor invoice documents in the accounts-payable subledger. Credit "
        "memos are excluded: a reversal legitimately repeats the vendor, "
        "amount and dates of the invoice it cancels."
    )
    criterion_description = (
        "Two or more invoices from the same vendor carry the same amount and "
        "references that name the same document — identical, or differing by "
        "one transposition of two digits. Distance in time is not part of "
        "the criterion: a vendor does not issue one reference twice, so a "
        "re-key found a period later is the same finding as one found the "
        "next day. A single differing digit is deliberately not a match."
    )
    limitations = (
        "Equal amounts are required. A re-key whose amount was altered — a "
        "partial payment, a revised invoice, a mistyped figure — meets no "
        "part of this criterion and is invisible to it.",
        "Vendors number sequentially, so a reference one digit away from "
        "another is ordinarily the vendor's next invoice. Matching single "
        "mis-keyed digits would buy recall at a false-positive cost this "
        "population cannot bound, and the screen refuses it.",
        "Progress billings that repeat a reference and happen to split a "
        "contract into equal instalments meet the criterion exactly and are "
        "flagged. The residual is small and named; it is not tuned away.",
        "A duplicate keyed under a genuinely unrelated reference carries no "
        "key to match. AP-002 covers that case on different evidence, with "
        "the different precision that implies.",
    )

    def __init__(self, allow_transposed: bool = True, window_days: int = None):
        # window_days=None is unbounded on purpose (see criterion). It is a
        # parameter because bounding it is an auditor scoping decision, and
        # because the report card must be able to grade the bounded variant:
        # a 7-day window is the naive port of the GL duplicate rule, and the
        # cross-period class exists to make that mis-tuning visible.
        self.allow_transposed = allow_transposed
        self.window_days = window_days

    def params(self):
        return {
            "allow_transposed": self.allow_transposed,
            "window_days": self.window_days,
        }

    def evaluate(self, ledger):
        partners = {}
        for _key, members in sorted(_group(self.population(ledger)).items()):
            if len(members) < 2:
                continue
            members.sort(key=lambda e: (e.posting_date, e.entry_id))
            for i, a in enumerate(members):
                for b in members[i + 1:]:
                    gap = abs((b.posting_date - a.posting_date).days)
                    if self.window_days is not None and gap > self.window_days:
                        continue
                    basis = reference_match(
                        a.document.reference, b.document.reference,
                        allow_transposed=self.allow_transposed,
                    )
                    if not basis:
                        continue
                    for this, other in ((a, b), (b, a)):
                        partners.setdefault(this.entry_id, []).append(
                            (other, basis, gap)
                        )
        flags = []
        for entry_id, hits in sorted(partners.items()):
            e = ledger.entry(entry_id)
            other, basis, gap = hits[0]
            others = ", ".join(sorted(o.entry_id for o, _b, _g in hits))
            word = (
                "under the same document reference"
                if basis == "exact"
                else f"under reference {other.document.reference}, one "
                     f"transposition of two digits away"
            )
            flags.append(
                Flag(
                    self.rule_id,
                    entry_id,
                    f"Vendor {e.document.party_id} invoice "
                    f"{e.document.reference} for "
                    f"{cents_to_str(e.amount_cents)} matches {others} on "
                    f"vendor and amount, {word}, keyed {gap} day(s) apart",
                    {
                        "partners": sorted(o.entry_id for o, _b, _g in hits),
                        "basis": basis,
                        "vendor_id": e.document.party_id,
                        "reference": e.document.reference,
                        "posting_gap_days": gap,
                    },
                )
            )
        return sort_flags(flags)


class DuplicateInvoiceAmountDateRule(_APRule):
    rule_id = "AP-002"
    title = "Duplicate vendor invoices without a matching reference"
    targets = ("ap_no_reference_match",)
    references = ("AU-C 240",)
    population_description = (
        "Vendor invoice documents in the accounts-payable subledger. Credit "
        "memos are excluded by default: a reversal carries the vendor, "
        "amount and dates of the invoice it cancels, and every one of them "
        "would meet this criterion."
    )
    criterion_description = (
        "Two invoices from the same vendor carry the same amount and "
        "invoice dates within the window, and their references do not name "
        "the same document (those pairs are AP-001's). The invoice date, "
        "not the posting date, bounds the window: the same document keyed "
        "twice carries one document date however long the second keying "
        "took."
    )
    limitations = (
        "This screen cannot distinguish a re-key from legitimate split "
        "billing — one delivery invoiced in parts on the same date, with "
        "the same amount and unrelated references, is the same object as far "
        "as the criterion can see. Its precision is capped by how much split "
        "billing the population contains, and the report card prints what "
        "that cap actually costs.",
        "Equal amounts are required, so a re-key with any amount difference "
        "is invisible here as it is to AP-001.",
        "The window is a materiality choice about invoice dates, calibrated "
        "against clean populations rather than taste; a duplicate entered "
        "under an invoice date further away than the window is out of scope "
        "and stated as such, not silently missed.",
        "Credit memos are outside the population. Including them would flag "
        "every reversal in the subledger; that scoping is a parameter, and "
        "its default is not a silent one.",
    )

    def __init__(
        self,
        window_days: int = DEFAULT_INVOICE_DATE_WINDOW,
        allow_transposed: bool = True,
        include_credit_memos: bool = False,
    ):
        if window_days < 0:
            raise ValueError("window_days must be non-negative")
        self.window_days = window_days
        self.allow_transposed = allow_transposed
        self.include_credit_memos = include_credit_memos

    def params(self):
        return {
            "window_days": self.window_days,
            "allow_transposed": self.allow_transposed,
            "include_credit_memos": self.include_credit_memos,
        }

    def evaluate(self, ledger):
        partners = {}
        for _key, members in sorted(_group(self.population(ledger)).items()):
            if len(members) < 2:
                continue
            members.sort(key=lambda e: (e.document.doc_date, e.entry_id))
            for i, a in enumerate(members):
                for b in members[i + 1:]:
                    gap = (b.document.doc_date - a.document.doc_date).days
                    if gap > self.window_days:
                        break
                    if reference_match(
                        a.document.reference, b.document.reference,
                        allow_transposed=self.allow_transposed,
                    ):
                        continue  # a key match exists; AP-001 owns the pair
                    for this, other in ((a, b), (b, a)):
                        partners.setdefault(this.entry_id, []).append((other, gap))
        flags = []
        for entry_id, hits in sorted(partners.items()):
            e = ledger.entry(entry_id)
            others = ", ".join(sorted(o.entry_id for o, _g in hits))
            gap = hits[0][1]
            flags.append(
                Flag(
                    self.rule_id,
                    entry_id,
                    f"Vendor {e.document.party_id} invoice "
                    f"{e.document.reference} for "
                    f"{cents_to_str(e.amount_cents)} matches {others} on "
                    f"vendor, amount and an invoice date {gap} day(s) apart, "
                    f"with no reference in common — a re-key and split "
                    f"billing look alike here",
                    {
                        "partners": sorted(o.entry_id for o, _g in hits),
                        "vendor_id": e.document.party_id,
                        "reference": e.document.reference,
                        "doc_date_gap_days": gap,
                    },
                )
            )
        return sort_flags(flags)
