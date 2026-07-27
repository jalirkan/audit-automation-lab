import unittest
from datetime import date

from ledger.model import (
    Account,
    ChartOfAccounts,
    JournalEntry,
    JournalLine,
    Ledger,
    User,
)
from rules.library import (
    BelowThresholdRule,
    DormantAccountRule,
    DuplicateRule,
    NearDuplicateRule,
    PeriodEndPostingRule,
    RarePairingRule,
    RoundDollarRule,
    SelfApprovalRule,
    ShortDescriptionRule,
    UnbalancedEntryRule,
    WeekendHolidayRule,
)


def _coa(extra=()):
    accounts = [
        Account("1000", "Cash", "asset", "debit"),
        Account("1100", "AR", "asset", "debit"),
        Account("2000", "AP", "liability", "credit"),
        Account("2100", "Accrued", "liability", "credit"),
        Account("4000", "Revenue", "revenue", "credit"),
        Account("6300", "Travel", "expense", "debit"),
        Account("6700", "Interest", "expense", "debit"),
        Account("6900", "Misc", "expense", "debit"),
    ]
    accounts.extend(extra)
    return ChartOfAccounts(accounts)


USERS = (
    User("P-01", "Pat", "preparer"),
    User("P-02", "Quinn", "preparer"),
    User("A-01", "Al", "approver"),
)

META = {
    "fiscal_year_end": "2025-12-31",
    "fiscal_year_start": "2025-01-01",
    "approval_threshold_cents": 1_000_000,
    "seed": 0,
}


def mk_entry(
    eid,
    posting,
    amount=5_000_00,
    debit="6900",
    credit="1000",
    desc="A perfectly ordinary test entry",
    source="GL",
    preparer="P-01",
    approver="A-01",
    effective=None,
    lines=None,
):
    return JournalEntry(
        entry_id=eid,
        posting_date=posting,
        effective_date=effective or posting,
        description=desc,
        source=source,
        preparer_id=preparer,
        approver_id=approver,
        lines=lines
        or (
            JournalLine(debit, debit_cents=amount),
            JournalLine(credit, credit_cents=amount),
        ),
    )


def mk_ledger(entries, coa=None, meta=None):
    return Ledger(
        coa=coa or _coa(),
        users=USERS,
        entries=tuple(entries),
        meta=dict(META if meta is None else meta),
    )


def flagged_ids(rule, ledger):
    return {f.entry_id for f in rule.evaluate(ledger)}


class UnbalancedTests(unittest.TestCase):
    def test_trigger_and_pass(self):
        bad = mk_entry(
            "JE-000001",
            date(2025, 3, 10),
            lines=(
                JournalLine("6900", debit_cents=100_00),
                JournalLine("1000", credit_cents=90_00),
            ),
        )
        good = mk_entry("JE-000002", date(2025, 3, 11))
        led = mk_ledger([bad, good])
        flags = UnbalancedEntryRule().evaluate(led)
        self.assertEqual([f.entry_id for f in flags], ["JE-000001"])
        self.assertIn("out of balance by 10.00", flags[0].rationale)


class PeriodEndTests(unittest.TestCase):
    def test_final_day_and_post_close_trigger(self):
        window_hit = mk_entry("JE-000001", date(2025, 12, 31))
        post_close = mk_entry(
            "JE-000002", date(2026, 1, 6), effective=date(2025, 12, 31)
        )
        mid_year = mk_entry("JE-000003", date(2025, 6, 10))
        second_last = mk_entry("JE-000004", date(2025, 12, 30))
        led = mk_ledger([window_hit, mid_year, second_last, post_close])
        rule = PeriodEndPostingRule(window_business_days=1)
        flags = {f.entry_id: f for f in rule.evaluate(led)}
        self.assertEqual(set(flags), {"JE-000001", "JE-000002"})
        self.assertEqual(flags["JE-000002"].details["kind"], "post_close")
        self.assertTrue(flags["JE-000002"].details["backdated"])

    def test_missing_fiscal_year_end_is_inapplicable(self):
        led = mk_ledger([mk_entry("JE-000001", date(2025, 6, 2))], meta={})
        ok, reason = PeriodEndPostingRule().applicable(led)
        self.assertFalse(ok)
        self.assertIn("fiscal year end", reason)


class WeekendHolidayTests(unittest.TestCase):
    def test_weekend_holiday_and_exclusion(self):
        sunday = mk_entry("JE-000001", date(2025, 3, 9))
        holiday = mk_entry("JE-000002", date(2025, 7, 4))  # Friday, July 4
        monday = mk_entry("JE-000003", date(2025, 3, 10))
        sys_weekend = mk_entry(
            "JE-000004", date(2025, 8, 31), source="SYS", preparer="P-02"
        )
        led = mk_ledger([sunday, holiday, monday, sys_weekend])
        self.assertEqual(
            flagged_ids(WeekendHolidayRule(), led),
            {"JE-000001", "JE-000002", "JE-000004"},
        )
        self.assertEqual(
            flagged_ids(WeekendHolidayRule(exclude_sources=("SYS",)), led),
            {"JE-000001", "JE-000002"},
        )


class RoundDollarTests(unittest.TestCase):
    def test_multiple_of_1000_at_or_above_minimum(self):
        round_big = mk_entry("JE-000001", date(2025, 5, 5), amount=15_000_00)
        not_round = mk_entry("JE-000002", date(2025, 5, 6), amount=15_000_50)
        round_small = mk_entry("JE-000003", date(2025, 5, 7), amount=500_00)
        led = mk_ledger([round_big, not_round, round_small])
        rule = RoundDollarRule()
        self.assertEqual(flagged_ids(rule, led), {"JE-000001"})
        # population excludes the below-minimum entry entirely
        self.assertEqual(rule.population_size(led), 2)


class BelowThresholdTests(unittest.TestCase):
    def test_band_and_cluster(self):
        in_band_a = mk_entry(
            "JE-000001", date(2025, 4, 1), amount=9_700_00, source="AP", approver=None
        )
        in_band_b = mk_entry(
            "JE-000002", date(2025, 4, 8), amount=9_650_00, source="AP", approver=None
        )
        below_band = mk_entry(
            "JE-000003", date(2025, 4, 2), amount=9_000_00, source="AP", approver=None
        )
        at_threshold = mk_entry(
            "JE-000004", date(2025, 4, 3), amount=10_000_00, source="AP"
        )
        led = mk_ledger([in_band_a, below_band, at_threshold, in_band_b])
        rule = BelowThresholdRule()
        flags = {f.entry_id: f for f in rule.evaluate(led)}
        self.assertEqual(set(flags), {"JE-000001", "JE-000002"})
        self.assertEqual(flags["JE-000001"].details["cluster"], ["JE-000002"])
        self.assertIn("below the 10000.00 approval threshold", flags["JE-000001"].rationale)

    def test_no_threshold_is_inapplicable(self):
        led = mk_ledger([mk_entry("JE-000001", date(2025, 4, 1))], meta={})
        ok, _ = BelowThresholdRule().applicable(led)
        self.assertFalse(ok)


class ShortDescriptionTests(unittest.TestCase):
    def test_blank_short_and_boilerplate(self):
        blank = mk_entry("JE-000001", date(2025, 2, 3), desc="")
        short = mk_entry("JE-000002", date(2025, 2, 4), desc="fix")
        boiler = mk_entry("JE-000003", date(2025, 2, 5), desc="Adjustment")
        fine = mk_entry("JE-000004", date(2025, 2, 6))
        led = mk_ledger([blank, short, boiler, fine])
        self.assertEqual(
            flagged_ids(ShortDescriptionRule(), led),
            {"JE-000001", "JE-000002", "JE-000003"},
        )


class DormantAccountTests(unittest.TestCase):
    def test_inactive_and_stale_accounts_trigger_once(self):
        coa = _coa(
            extra=(
                Account("4500", "Discontinued revenue", "revenue", "credit",
                        active=False, last_activity_before_range=date(2023, 3, 31)),
                Account("1300", "Prepaid", "asset", "debit",
                        active=True, last_activity_before_range=date(2024, 1, 31)),
            )
        )
        to_inactive = mk_entry(
            "JE-000001",
            date(2025, 6, 2),
            lines=(
                JournalLine("1100", debit_cents=50_00),
                JournalLine("4500", credit_cents=50_00),
            ),
        )
        again_inactive = mk_entry(
            "JE-000002",
            date(2025, 6, 9),
            lines=(
                JournalLine("1100", debit_cents=60_00),
                JournalLine("4500", credit_cents=60_00),
            ),
        )
        to_stale_active = mk_entry(
            "JE-000003",
            date(2025, 6, 10),
            lines=(
                JournalLine("1300", debit_cents=70_00),
                JournalLine("1000", credit_cents=70_00),
            ),
        )
        normal = mk_entry("JE-000004", date(2025, 6, 11))
        led = mk_ledger([to_inactive, again_inactive, to_stale_active, normal], coa=coa)
        rule = DormantAccountRule()
        flags = {f.entry_id: f for f in rule.evaluate(led)}
        # First posting to 4500: inactive + stale. Second: still inactive
        # (marked in the chart) but no longer stale — the in-range history
        # keeps it flagged for inactivity only.
        self.assertIn("JE-000001", flags)
        self.assertIn("794 days", flags["JE-000001"].rationale)
        self.assertIn("JE-000002", flags)
        self.assertNotIn("days)", flags["JE-000002"].rationale)
        # Active-but-stale account triggers on declared history alone.
        self.assertIn("JE-000003", flags)
        self.assertNotIn("JE-000004", flags)


class RarePairingTests(unittest.TestCase):
    def test_unique_pair_flagged(self):
        common_a = mk_entry("JE-000001", date(2025, 3, 3))
        common_b = mk_entry("JE-000002", date(2025, 3, 4))
        rare = mk_entry(
            "JE-000003",
            date(2025, 3, 5),
            lines=(
                JournalLine("6700", debit_cents=80_00),
                JournalLine("4000", credit_cents=80_00),
            ),
        )
        led = mk_ledger([common_a, common_b, rare])
        rule = RarePairingRule(max_count=1, min_population=1)
        flags = rule.evaluate(led)
        self.assertEqual([f.entry_id for f in flags], ["JE-000003"])
        self.assertIn("DR 6700 / CR 4000 (seen 1x in 3 entries)", flags[0].rationale)

    def test_small_population_refuses(self):
        led = mk_ledger([mk_entry("JE-000001", date(2025, 3, 3))])
        rule = RarePairingRule()  # default min_population=500
        ok, reason = rule.applicable(led)
        self.assertFalse(ok)
        self.assertIn("below minimum", reason)
        self.assertEqual(rule.evaluate(led), [])


class SelfApprovalTests(unittest.TestCase):
    def test_self_approval_and_missing_approval(self):
        selfie = mk_entry("JE-000001", date(2025, 5, 5), approver="P-01")
        missing = mk_entry(
            "JE-000002", date(2025, 5, 6), amount=12_000_00, source="REV", approver=None
        )
        proper = mk_entry("JE-000003", date(2025, 5, 7))
        small_rev = mk_entry(
            "JE-000004", date(2025, 5, 8), amount=100_00, source="REV", approver=None
        )
        led = mk_ledger([selfie, missing, proper, small_rev])
        rule = SelfApprovalRule()
        flags = {f.entry_id: f for f in rule.evaluate(led)}
        self.assertEqual(set(flags), {"JE-000001", "JE-000002"})
        self.assertEqual(flags["JE-000001"].details["kind"], "self_approval")
        self.assertEqual(flags["JE-000002"].details["kind"], "missing_approval")
        # small revenue entry is outside the population, not a pass
        self.assertEqual(rule.population_size(led), 3)


class DuplicateTests(unittest.TestCase):
    def test_identical_within_window(self):
        a = mk_entry("JE-000001", date(2025, 6, 2), amount=750_25, source="AP")
        b = mk_entry("JE-000002", date(2025, 6, 4), amount=750_25, source="AP")
        far = mk_entry("JE-000003", date(2025, 6, 25), amount=750_25, source="AP")
        different = mk_entry("JE-000004", date(2025, 6, 3), amount=750_26, source="AP")
        led = mk_ledger([a, b, different, far])
        flags = {f.entry_id: f for f in DuplicateRule().evaluate(led)}
        self.assertEqual(set(flags), {"JE-000001", "JE-000002"})
        self.assertEqual(flags["JE-000001"].details["partners"], ["JE-000002"])

    def test_other_preparer_not_grouped(self):
        a = mk_entry("JE-000001", date(2025, 6, 2), amount=750_25)
        b = mk_entry("JE-000002", date(2025, 6, 4), amount=750_25, preparer="P-02")
        led = mk_ledger([a, b])
        self.assertEqual(flagged_ids(DuplicateRule(), led), set())


class NearDuplicateTests(unittest.TestCase):
    def test_shifted_amount_resubmission(self):
        a = mk_entry(
            "JE-000001",
            date(2025, 6, 2),
            amount=950_00,
            debit="6300",
            credit="2000",
            desc="Bluepine Logistics inv 44821",
            source="AP",
        )
        b = mk_entry(
            "JE-000002",
            date(2025, 6, 5),
            amount=956_65,
            debit="6300",
            credit="2000",
            desc="Bluepine Logistics inv 44821 (resubmitted)",
            source="AP",
        )
        led = mk_ledger([a, b])
        flags = {f.entry_id: f for f in NearDuplicateRule().evaluate(led)}
        self.assertEqual(set(flags), {"JE-000001", "JE-000002"})
        self.assertEqual(flags["JE-000001"].details["partner"], "JE-000002")

    def test_exact_duplicates_left_to_r010(self):
        a = mk_entry("JE-000001", date(2025, 6, 2), amount=950_00, desc="Same words")
        b = mk_entry("JE-000002", date(2025, 6, 4), amount=950_00, desc="Same words")
        led = mk_ledger([a, b])
        self.assertEqual(flagged_ids(NearDuplicateRule(), led), set())

    def test_amount_gap_or_dissimilar_text_not_flagged(self):
        a = mk_entry("JE-000001", date(2025, 6, 2), amount=950_00, desc="Northwind inv 1")
        wide = mk_entry("JE-000002", date(2025, 6, 4), amount=999_00, desc="Northwind inv 2")
        dissimilar = mk_entry(
            "JE-000003", date(2025, 6, 5), amount=951_00, desc="zq"
        )
        led = mk_ledger([a, wide, dissimilar])
        self.assertEqual(flagged_ids(NearDuplicateRule(), led), set())


if __name__ == "__main__":
    unittest.main()
