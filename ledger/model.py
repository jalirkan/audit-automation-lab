"""Domain model: chart of accounts, users, journal entries, ledger.

Money is integer cents throughout (DECISIONS D-006): float money is a
rounding bug factory, and digit-based analytics (Benford) are unaffected
because leading significant digits are invariant under the ×100 scale.

Validation here is structural only (types, non-negative one-sided lines,
non-empty line lists). The model deliberately *permits* anomalies —
unbalanced entries, blank descriptions, self-approval — because detecting
those is the point of the lab; a model that refused to represent them could
never carry a planted anomaly to the rules that must find it.
"""

from dataclasses import dataclass, field
from datetime import date

from core.dates import period_str

ACCOUNT_TYPES = ("asset", "liability", "equity", "revenue", "expense")
NORMAL_SIDES = ("debit", "credit")
USER_ROLES = ("preparer", "approver", "system")
DOC_TYPES = ("invoice", "credit_memo")


def cents_to_str(cents: int) -> str:
    """Format integer cents as a plain decimal string, e.g. 123456 -> '1234.56'."""
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"


@dataclass(frozen=True)
class Account:
    account_id: str
    name: str
    type: str
    normal_side: str
    active: bool = True
    # For dormant accounts: last known posting date before the generated
    # range. None means no history is asserted.
    last_activity_before_range: date = None

    def __post_init__(self):
        if self.type not in ACCOUNT_TYPES:
            raise ValueError(f"unknown account type: {self.type!r}")
        if self.normal_side not in NORMAL_SIDES:
            raise ValueError(f"unknown normal side: {self.normal_side!r}")
        if not self.account_id:
            raise ValueError("account_id must be non-empty")

    def to_dict(self) -> dict:
        return {
            "account_id": self.account_id,
            "name": self.name,
            "type": self.type,
            "normal_side": self.normal_side,
            "active": self.active,
            "last_activity_before_range": (
                self.last_activity_before_range.isoformat()
                if self.last_activity_before_range
                else None
            ),
        }

    @staticmethod
    def from_dict(d: dict) -> "Account":
        lab = d.get("last_activity_before_range")
        return Account(
            account_id=d["account_id"],
            name=d["name"],
            type=d["type"],
            normal_side=d["normal_side"],
            active=d["active"],
            last_activity_before_range=date.fromisoformat(lab) if lab else None,
        )


class ChartOfAccounts:
    """Immutable-by-convention account registry keyed by account_id."""

    def __init__(self, accounts):
        self._accounts = {}
        for a in accounts:
            if a.account_id in self._accounts:
                raise ValueError(f"duplicate account_id: {a.account_id}")
            self._accounts[a.account_id] = a

    def get(self, account_id: str) -> Account:
        try:
            return self._accounts[account_id]
        except KeyError:
            raise KeyError(f"unknown account: {account_id}") from None

    def __contains__(self, account_id: str) -> bool:
        return account_id in self._accounts

    def ids(self) -> list:
        return sorted(self._accounts)

    def accounts(self) -> list:
        return [self._accounts[i] for i in self.ids()]

    def by_type(self, type_: str) -> list:
        return [a for a in self.accounts() if a.type == type_]

    def inactive_ids(self) -> list:
        return [a.account_id for a in self.accounts() if not a.active]

    def to_list(self) -> list:
        return [a.to_dict() for a in self.accounts()]

    @staticmethod
    def from_list(items) -> "ChartOfAccounts":
        return ChartOfAccounts([Account.from_dict(d) for d in items])


@dataclass(frozen=True)
class User:
    user_id: str
    name: str
    role: str

    def __post_init__(self):
        if self.role not in USER_ROLES:
            raise ValueError(f"unknown role: {self.role!r}")

    def to_dict(self) -> dict:
        return {"user_id": self.user_id, "name": self.name, "role": self.role}

    @staticmethod
    def from_dict(d: dict) -> "User":
        return User(d["user_id"], d["name"], d["role"])


@dataclass(frozen=True)
class JournalLine:
    account_id: str
    debit_cents: int = 0
    credit_cents: int = 0

    def __post_init__(self):
        if not isinstance(self.debit_cents, int) or not isinstance(self.credit_cents, int):
            raise TypeError("line amounts must be integer cents")
        if self.debit_cents < 0 or self.credit_cents < 0:
            raise ValueError("line amounts must be non-negative")
        if (self.debit_cents > 0) == (self.credit_cents > 0):
            raise ValueError("exactly one of debit/credit must be positive")

    def to_dict(self) -> dict:
        return {
            "account_id": self.account_id,
            "debit_cents": self.debit_cents,
            "credit_cents": self.credit_cents,
        }

    @staticmethod
    def from_dict(d: dict) -> "JournalLine":
        return JournalLine(d["account_id"], d["debit_cents"], d["credit_cents"])


@dataclass(frozen=True)
class SourceDocument:
    """The subledger document an entry records.

    A general-ledger entry has no structured counterparty or document
    number: those live in free text, which is exactly why the GL's
    duplicate screens are lexical and say so (D-013). A subledger extract
    has them as fields, and the AP rules key on the fields rather than
    scraping prose (DECISIONS D-033). Optional on JournalEntry: GL entries
    carry none, and their serialization is unchanged.
    """

    doc_type: str        # one of DOC_TYPES
    party_id: str        # vendor (AP) or customer (AR) identifier
    reference: str       # the counterparty's own document number
    doc_date: date       # the document's date, not the date it was keyed

    def __post_init__(self):
        if self.doc_type not in DOC_TYPES:
            raise ValueError(f"unknown document type: {self.doc_type!r}")
        if not self.party_id:
            raise ValueError("party_id must be non-empty")
        if not self.reference:
            raise ValueError("reference must be non-empty")
        if not isinstance(self.doc_date, date):
            raise TypeError("doc_date must be a date")

    def to_dict(self) -> dict:
        return {
            "doc_type": self.doc_type,
            "party_id": self.party_id,
            "reference": self.reference,
            "doc_date": self.doc_date.isoformat(),
        }

    @staticmethod
    def from_dict(d: dict) -> "SourceDocument":
        return SourceDocument(
            doc_type=d["doc_type"],
            party_id=d["party_id"],
            reference=d["reference"],
            doc_date=date.fromisoformat(d["doc_date"]),
        )


@dataclass(frozen=True)
class JournalEntry:
    entry_id: str
    posting_date: date
    effective_date: date
    description: str
    source: str
    preparer_id: str
    approver_id: str  # None when no approval is recorded
    lines: tuple
    document: SourceDocument = None  # subledger entries only

    def __post_init__(self):
        if not self.lines:
            raise ValueError("entry must have at least one line")
        if not isinstance(self.lines, tuple):
            raise TypeError("lines must be a tuple")
        if self.document is not None and not isinstance(self.document, SourceDocument):
            raise TypeError("document must be a SourceDocument")

    @property
    def total_debits_cents(self) -> int:
        return sum(l.debit_cents for l in self.lines)

    @property
    def total_credits_cents(self) -> int:
        return sum(l.credit_cents for l in self.lines)

    @property
    def amount_cents(self) -> int:
        """Entry magnitude: max of the two sides (equal when balanced)."""
        return max(self.total_debits_cents, self.total_credits_cents)

    @property
    def is_balanced(self) -> bool:
        return self.total_debits_cents == self.total_credits_cents

    @property
    def period(self) -> str:
        """Fiscal period, from the effective date (calendar-month convention)."""
        return period_str(self.effective_date)

    @property
    def account_ids(self) -> tuple:
        return tuple(sorted({l.account_id for l in self.lines}))

    @property
    def debit_account_ids(self) -> tuple:
        return tuple(sorted({l.account_id for l in self.lines if l.debit_cents > 0}))

    @property
    def credit_account_ids(self) -> tuple:
        return tuple(sorted({l.account_id for l in self.lines if l.credit_cents > 0}))

    def to_dict(self) -> dict:
        d = {
            "entry_id": self.entry_id,
            "posting_date": self.posting_date.isoformat(),
            "effective_date": self.effective_date.isoformat(),
            "description": self.description,
            "source": self.source,
            "preparer_id": self.preparer_id,
            "approver_id": self.approver_id,
            "lines": [l.to_dict() for l in self.lines],
        }
        # Absent, not null: a GL entry records no subledger document, and
        # emitting a null for one would change the canonical bytes of every
        # ledger written before subledgers existed (D-007).
        if self.document is not None:
            d["document"] = self.document.to_dict()
        return d

    @staticmethod
    def from_dict(d: dict) -> "JournalEntry":
        doc = d.get("document")
        return JournalEntry(
            entry_id=d["entry_id"],
            posting_date=date.fromisoformat(d["posting_date"]),
            effective_date=date.fromisoformat(d["effective_date"]),
            description=d["description"],
            source=d["source"],
            preparer_id=d["preparer_id"],
            approver_id=d["approver_id"],
            lines=tuple(JournalLine.from_dict(x) for x in d["lines"]),
            document=SourceDocument.from_dict(doc) if doc else None,
        )


@dataclass
class Ledger:
    coa: ChartOfAccounts
    users: tuple
    entries: tuple
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        self._index = {}
        for e in self.entries:
            if e.entry_id in self._index:
                raise ValueError(f"duplicate entry_id: {e.entry_id}")
            self._index[e.entry_id] = e

    def entry(self, entry_id: str) -> JournalEntry:
        try:
            return self._index[entry_id]
        except KeyError:
            raise KeyError(f"unknown entry: {entry_id}") from None

    def __contains__(self, entry_id: str) -> bool:
        return entry_id in self._index

    def __len__(self) -> int:
        return len(self.entries)

    def user(self, user_id: str) -> User:
        for u in self.users:
            if u.user_id == user_id:
                return u
        raise KeyError(f"unknown user: {user_id}")

    def to_dict(self) -> dict:
        return {
            "meta": self.meta,
            "coa": self.coa.to_list(),
            "users": [u.to_dict() for u in sorted(self.users, key=lambda u: u.user_id)],
            "entries": [e.to_dict() for e in self.entries],
        }

    @staticmethod
    def from_dict(d: dict) -> "Ledger":
        return Ledger(
            coa=ChartOfAccounts.from_list(d["coa"]),
            users=tuple(User.from_dict(u) for u in d["users"]),
            entries=tuple(JournalEntry.from_dict(e) for e in d["entries"]),
            meta=dict(d["meta"]),
        )

    def entries_csv(self) -> str:
        """Flat CSV, one row per line; LF terminators for cross-platform
        byte-identity (DECISIONS D-007)."""
        import csv
        import io

        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(
            [
                "entry_id",
                "posting_date",
                "effective_date",
                "period",
                "source",
                "preparer_id",
                "approver_id",
                "description",
                "line_no",
                "account_id",
                "account_name",
                "debit",
                "credit",
                # Subledger document fields, appended so column positions in
                # a general-ledger export are unchanged; empty for entries
                # that record no document.
                "doc_type",
                "doc_party",
                "doc_reference",
                "doc_date",
            ]
        )
        for e in self.entries:
            doc = e.document
            for i, line in enumerate(e.lines, start=1):
                w.writerow(
                    [
                        e.entry_id,
                        e.posting_date.isoformat(),
                        e.effective_date.isoformat(),
                        e.period,
                        e.source,
                        e.preparer_id,
                        e.approver_id or "",
                        e.description,
                        i,
                        line.account_id,
                        self.coa.get(line.account_id).name if line.account_id in self.coa else "",
                        cents_to_str(line.debit_cents) if line.debit_cents else "",
                        cents_to_str(line.credit_cents) if line.credit_cents else "",
                        doc.doc_type if doc else "",
                        doc.party_id if doc else "",
                        doc.reference if doc else "",
                        doc.doc_date.isoformat() if doc else "",
                    ]
                )
        return buf.getvalue()
