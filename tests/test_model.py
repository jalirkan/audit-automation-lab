import unittest
from datetime import date

from core.canonical import canonical_bytes
from ledger.model import (
    Account,
    ChartOfAccounts,
    JournalEntry,
    JournalLine,
    Ledger,
    User,
    cents_to_str,
)


def _entry(entry_id="JE-000001", debit=10_00, credit=10_00, desc="A perfectly ordinary entry"):
    return JournalEntry(
        entry_id=entry_id,
        posting_date=date(2025, 3, 10),
        effective_date=date(2025, 3, 10),
        description=desc,
        source="GL",
        preparer_id="P-01",
        approver_id="A-01",
        lines=(
            JournalLine("6900", debit_cents=debit),
            JournalLine("1000", credit_cents=credit),
        ),
    )


class LineTests(unittest.TestCase):
    def test_one_sided_only(self):
        with self.assertRaises(ValueError):
            JournalLine("1000", debit_cents=5, credit_cents=5)
        with self.assertRaises(ValueError):
            JournalLine("1000")  # both zero

    def test_negative_rejected(self):
        with self.assertRaises(ValueError):
            JournalLine("1000", debit_cents=-1)

    def test_float_rejected(self):
        with self.assertRaises(TypeError):
            JournalLine("1000", debit_cents=1.5)


class EntryTests(unittest.TestCase):
    def test_balance_and_amount(self):
        e = _entry()
        self.assertTrue(e.is_balanced)
        self.assertEqual(e.amount_cents, 10_00)
        u = _entry(debit=12_00, credit=10_00)
        self.assertFalse(u.is_balanced)
        self.assertEqual(u.amount_cents, 12_00)

    def test_period_from_effective_date(self):
        e = JournalEntry(
            entry_id="JE-000002",
            posting_date=date(2026, 1, 5),
            effective_date=date(2025, 12, 31),
            description="Post-close example",
            source="GL",
            preparer_id="P-01",
            approver_id="A-01",
            lines=(JournalLine("1100", debit_cents=5_00), JournalLine("4000", credit_cents=5_00)),
        )
        self.assertEqual(e.period, "2025-12")

    def test_model_permits_anomalies(self):
        """The model must carry planted anomalies: blank description and an
        unbalanced entry are representable, not rejected."""
        e = _entry(desc="", debit=9_99, credit=5_00)
        self.assertEqual(e.description, "")
        self.assertFalse(e.is_balanced)

    def test_empty_lines_rejected(self):
        with self.assertRaises(ValueError):
            JournalEntry(
                entry_id="JE-000003",
                posting_date=date(2025, 1, 2),
                effective_date=date(2025, 1, 2),
                description="no lines",
                source="GL",
                preparer_id="P-01",
                approver_id=None,
                lines=(),
            )


class ChartTests(unittest.TestCase):
    def test_duplicate_account_rejected(self):
        a = Account("1000", "Cash", "asset", "debit")
        with self.assertRaises(ValueError):
            ChartOfAccounts([a, a])

    def test_bad_type_rejected(self):
        with self.assertRaises(ValueError):
            Account("1000", "Cash", "moneybucket", "debit")


class LedgerTests(unittest.TestCase):
    def _ledger(self):
        coa = ChartOfAccounts(
            [
                Account("1000", "Cash", "asset", "debit"),
                Account("4000", "Revenue", "revenue", "credit"),
                Account("6900", "Misc", "expense", "debit"),
                Account("1100", "AR", "asset", "debit"),
            ]
        )
        users = (User("P-01", "Pat", "preparer"), User("A-01", "Al", "approver"))
        return Ledger(coa=coa, users=users, entries=(_entry(),), meta={"seed": 1})

    def test_duplicate_entry_id_rejected(self):
        coa = ChartOfAccounts([Account("1000", "Cash", "asset", "debit"),
                               Account("6900", "Misc", "expense", "debit")])
        with self.assertRaises(ValueError):
            Ledger(coa=coa, users=(), entries=(_entry(), _entry()), meta={})

    def test_roundtrip_is_byte_identical(self):
        led = self._ledger()
        again = Ledger.from_dict(led.to_dict())
        self.assertEqual(canonical_bytes(led.to_dict()), canonical_bytes(again.to_dict()))

    def test_csv_shape(self):
        led = self._ledger()
        lines = led.entries_csv().splitlines()
        self.assertEqual(len(lines), 1 + 2)  # header + one entry of two lines
        self.assertTrue(lines[0].startswith("entry_id,"))

    def test_cents_to_str(self):
        self.assertEqual(cents_to_str(123456), "1234.56")
        self.assertEqual(cents_to_str(5), "0.05")
        self.assertEqual(cents_to_str(-2500), "-25.00")


if __name__ == "__main__":
    unittest.main()
