"""The rule library: eleven deterministic JE tests.

Every rule is a complete examination of its declared population (toolkit
D-031 framing: these are 100% examinations of a configured population, not
samples of a larger universe). All iteration is over ordered structures, so
two runs on the same ledger produce identical flags in identical order.
"""

from datetime import date, timedelta
from difflib import SequenceMatcher

from core.dates import holidays_for_range, last_n_business_days
from ledger.model import cents_to_str
from rules.base import Flag, Rule, sort_flags


def _threshold(ledger, override):
    if override is not None:
        return override
    return ledger.meta.get("approval_threshold_cents")


def _fy_end(ledger):
    raw = ledger.meta.get("fiscal_year_end")
    return date.fromisoformat(raw) if raw else None


def _ledger_holidays(ledger):
    if not ledger.entries:
        return frozenset()
    dates = [e.posting_date for e in ledger.entries]
    return holidays_for_range(min(dates), max(dates))


class UnbalancedEntryRule(Rule):
    rule_id = "R-001"
    title = "Unbalanced journal entries"
    targets = ("unbalanced_entry",)
    references = ("AU-C 240",)
    population_description = "All journal entries."
    criterion_description = "Total debits do not equal total credits."
    limitations = (
        "Most GL systems enforce balance at entry; imbalances typically "
        "indicate import or conversion defects rather than manual activity.",
    )

    def evaluate(self, ledger):
        flags = []
        for e in ledger.entries:
            if not e.is_balanced:
                diff = e.total_debits_cents - e.total_credits_cents
                flags.append(
                    Flag(
                        self.rule_id,
                        e.entry_id,
                        f"Debits {cents_to_str(e.total_debits_cents)} vs credits "
                        f"{cents_to_str(e.total_credits_cents)}: entry is out of "
                        f"balance by {cents_to_str(abs(diff))}",
                        {"difference_cents": diff},
                    )
                )
        return sort_flags(flags)


class PeriodEndPostingRule(Rule):
    rule_id = "R-002"
    title = "Entries at or after fiscal year end"
    targets = ("late_round_dollar", "post_close_entry")
    references = ("AU-C 240", "ISA 240")
    population_description = "All journal entries."
    criterion_description = (
        "Posted within the final N business days of the fiscal year, or "
        "posted after fiscal year end (including entries effective back into "
        "the closed period)."
    )
    limitations = (
        "A period-end selection sweeps in legitimate close activity by "
        "design; its yield is a review population, not an exception list.",
    )

    def __init__(self, window_business_days: int = 1):
        self.window_business_days = window_business_days

    def params(self):
        return {"window_business_days": self.window_business_days}

    def applicable(self, ledger):
        if _fy_end(ledger) is None:
            return False, "ledger metadata does not declare a fiscal year end"
        return True, ""

    def evaluate(self, ledger):
        fy_end = _fy_end(ledger)
        holidays = _ledger_holidays(ledger)
        window = last_n_business_days(fy_end, self.window_business_days, holidays)
        flags = []
        for e in ledger.entries:
            if e.posting_date in window:
                flags.append(
                    Flag(
                        self.rule_id,
                        e.entry_id,
                        f"Posted {e.posting_date.isoformat()}, within the final "
                        f"{self.window_business_days} business day(s) of the "
                        f"fiscal year",
                        {"kind": "period_end_window"},
                    )
                )
            elif e.posting_date > fy_end:
                backdated = e.effective_date <= fy_end
                rationale = (
                    f"Posted {e.posting_date.isoformat()}, after fiscal year end"
                )
                if backdated:
                    rationale += (
                        f", effective {e.effective_date.isoformat()} back into "
                        f"the closed period"
                    )
                flags.append(
                    Flag(
                        self.rule_id,
                        e.entry_id,
                        rationale,
                        {"kind": "post_close", "backdated": backdated},
                    )
                )
        return sort_flags(flags)


class WeekendHolidayRule(Rule):
    rule_id = "R-003"
    title = "Weekend and holiday postings"
    targets = ("weekend_manual",)
    references = ("AU-C 240",)
    population_description = (
        "All journal entries (sources excluded by parameter are listed in the "
        "workpaper)."
    )
    criterion_description = (
        "Posting date falls on a weekend or an observed US federal holiday."
    )
    limitations = (
        "Automated batch sources legitimately post on calendar month-ends "
        "that fall on weekends; excluding them is an auditor scoping "
        "decision, recorded in parameters, not a property of the data.",
    )

    def __init__(self, exclude_sources: tuple = ()):
        self.exclude_sources = tuple(exclude_sources)

    def params(self):
        return {"exclude_sources": list(self.exclude_sources)}

    def population(self, ledger):
        return [e for e in ledger.entries if e.source not in self.exclude_sources]

    def evaluate(self, ledger):
        holidays = _ledger_holidays(ledger)
        flags = []
        for e in self.population(ledger):
            d = e.posting_date
            if d.weekday() >= 5:
                reason = f"a {d.strftime('%A')}"
            elif d in holidays:
                reason = "an observed US federal holiday"
            else:
                continue
            flags.append(
                Flag(
                    self.rule_id,
                    e.entry_id,
                    f"Posted {d.isoformat()}, {reason}, by {e.preparer_id} "
                    f"(source {e.source})",
                    {"weekday": d.weekday()},
                )
            )
        return sort_flags(flags)


class RoundDollarRule(Rule):
    rule_id = "R-004"
    title = "Large exact round-dollar entries"
    targets = ("late_round_dollar",)
    references = ("AU-C 240", "ISA 240")
    population_description = "Journal entries at or above the minimum amount."
    criterion_description = (
        "Entry amount is an exact multiple of the round unit (default $1,000)."
    )
    limitations = (
        "Contractual amounts (rents, fees) are legitimately round; the flag "
        "is a lead precisely because round amounts are also how estimates "
        "and fabricated entries tend to be keyed.",
    )

    def __init__(self, round_to_cents: int = 100_000, min_cents: int = 100_000):
        if round_to_cents <= 0:
            raise ValueError("round_to_cents must be positive")
        self.round_to_cents = round_to_cents
        self.min_cents = min_cents

    def params(self):
        return {"round_to_cents": self.round_to_cents, "min_cents": self.min_cents}

    def population(self, ledger):
        return [e for e in ledger.entries if e.amount_cents >= self.min_cents]

    def evaluate(self, ledger):
        flags = []
        for e in self.population(ledger):
            if e.amount_cents % self.round_to_cents == 0:
                flags.append(
                    Flag(
                        self.rule_id,
                        e.entry_id,
                        f"Amount {cents_to_str(e.amount_cents)} is an exact "
                        f"multiple of {cents_to_str(self.round_to_cents)}",
                        {"amount_cents": e.amount_cents},
                    )
                )
        return sort_flags(flags)


class BelowThresholdRule(Rule):
    rule_id = "R-005"
    title = "Amounts just below the approval threshold"
    targets = ("threshold_shaving",)
    references = ("AU-C 240",)
    population_description = "Journal entries below the approval threshold."
    criterion_description = (
        "Amount falls within the band immediately below the approval "
        "threshold; the rationale notes other in-band entries by the same "
        "preparer within the clustering window."
    )
    limitations = (
        "Amounts near a threshold occur legitimately; the lead strengthens "
        "when several such entries share a preparer within a short window.",
    )

    def __init__(self, band_cents: int = 65_000, cluster_window_days: int = 15,
                 threshold_cents: int = None):
        self.band_cents = band_cents
        self.cluster_window_days = cluster_window_days
        self.threshold_cents = threshold_cents

    def params(self):
        return {
            "band_cents": self.band_cents,
            "cluster_window_days": self.cluster_window_days,
            "threshold_cents": self.threshold_cents,
        }

    def applicable(self, ledger):
        if _threshold(ledger, self.threshold_cents) is None:
            return False, "no approval threshold configured or in ledger metadata"
        return True, ""

    def population(self, ledger):
        threshold = _threshold(ledger, self.threshold_cents)
        if threshold is None:
            return []
        return [e for e in ledger.entries if e.amount_cents < threshold]

    def evaluate(self, ledger):
        threshold = _threshold(ledger, self.threshold_cents)
        if threshold is None:
            return []
        in_band = [
            e
            for e in self.population(ledger)
            if threshold - self.band_cents <= e.amount_cents < threshold
        ]
        flags = []
        for e in in_band:
            cluster = [
                o.entry_id
                for o in in_band
                if o.preparer_id == e.preparer_id
                and o.entry_id != e.entry_id
                and abs((o.posting_date - e.posting_date).days)
                <= self.cluster_window_days
            ]
            gap = threshold - e.amount_cents
            rationale = (
                f"Amount {cents_to_str(e.amount_cents)} is "
                f"{cents_to_str(gap)} below the {cents_to_str(threshold)} "
                f"approval threshold"
            )
            if cluster:
                rationale += (
                    f"; {len(cluster)} further below-threshold entr"
                    f"{'y' if len(cluster) == 1 else 'ies'} by {e.preparer_id} "
                    f"within {self.cluster_window_days} days "
                    f"({', '.join(sorted(cluster))})"
                )
            flags.append(
                Flag(
                    self.rule_id,
                    e.entry_id,
                    rationale,
                    {"gap_cents": gap, "cluster": sorted(cluster)},
                )
            )
        return sort_flags(flags)


class ShortDescriptionRule(Rule):
    rule_id = "R-006"
    title = "Missing or uninformative descriptions"
    targets = ("missing_description",)
    references = ("AU-C 240",)
    population_description = "All journal entries."
    criterion_description = (
        "Description is blank, shorter than the minimum length, or consists "
        "of a boilerplate token (e.g. 'misc', 'adjustment')."
    )
    limitations = (
        "Description quality is a proxy for reviewability, not for intent.",
    )

    BOILERPLATE = frozenset(
        {"misc", "adjustment", "adj", "correction", "n/a", "na", "je", "entry"}
    )

    def __init__(self, min_chars: int = 10):
        self.min_chars = min_chars

    def params(self):
        return {"min_chars": self.min_chars, "boilerplate": sorted(self.BOILERPLATE)}

    def evaluate(self, ledger):
        flags = []
        for e in ledger.entries:
            text = e.description.strip()
            if not text:
                rationale = "Entry has no description"
            elif len(text) < self.min_chars:
                rationale = (
                    f"Description {text!r} is shorter than {self.min_chars} "
                    f"characters"
                )
            elif text.lower() in self.BOILERPLATE:
                rationale = f"Description {text!r} is a boilerplate token"
            else:
                continue
            flags.append(
                Flag(self.rule_id, e.entry_id, rationale, {"description": text})
            )
        return sort_flags(flags)


class DormantAccountRule(Rule):
    rule_id = "R-007"
    title = "Postings to dormant accounts"
    targets = ("dormant_reactivation",)
    references = ("AU-C 240",)
    # The population is journal ENTRIES, which is what `population()` returns
    # and what `population_size` counts. This said "All journal entry lines."
    # while reporting a size of 100,051 — the entry count, against a ledger of
    # 200,128 lines — so a reader dividing findings by the stated population
    # computed a per-line rate on an entry denominator, wrong by nearly a factor
    # of two. The criterion below stays line-wise, because that is the test
    # applied within each entry; the shape follows R-008's, which already names
    # what it examines inside the parentheses.
    population_description = "All journal entries (postings examined line by line)."
    criterion_description = (
        "A line posts to an account flagged inactive in the chart of "
        "accounts, or to an account whose most recent prior activity "
        "(in-ledger or declared) is more than the dormancy window before "
        "the posting date."
    )
    limitations = (
        "Dormancy is judged against declared account history plus activity "
        "inside this ledger only; activity outside the extract is invisible.",
    )

    def __init__(self, dormant_days: int = 365):
        self.dormant_days = dormant_days

    def params(self):
        return {"dormant_days": self.dormant_days}

    def evaluate(self, ledger):
        # Prior in-range activity per account, walked in posting order.
        last_seen = {}
        flags = []
        for e in ledger.entries:
            for acct_id in e.account_ids:
                acct = ledger.coa.get(acct_id) if acct_id in ledger.coa else None
                prior = last_seen.get(acct_id)
                declared = acct.last_activity_before_range if acct else None
                reference = prior or declared
                reasons = []
                if acct is not None and not acct.active:
                    reasons.append(
                        f"account {acct_id} ({acct.name}) is marked inactive"
                    )
                if (
                    reference is not None
                    and prior is None
                    and (e.posting_date - reference).days > self.dormant_days
                ):
                    reasons.append(
                        f"no activity in account {acct_id} since "
                        f"{reference.isoformat()} "
                        f"({(e.posting_date - reference).days} days)"
                    )
                if reasons:
                    flags.append(
                        Flag(
                            self.rule_id,
                            e.entry_id,
                            "First posting after dormancy: " + "; ".join(reasons),
                            {"account_id": acct_id},
                        )
                    )
                last_seen[acct_id] = e.posting_date
        # One flag per entry (an entry touching two dormant accounts reads as
        # one lead with both reasons).
        merged = {}
        for f in flags:
            if f.entry_id in merged:
                prev = merged[f.entry_id]
                merged[f.entry_id] = Flag(
                    self.rule_id,
                    f.entry_id,
                    prev.rationale + " | " + f.rationale,
                    {"account_ids": sorted({prev.details.get("account_id"), f.details.get("account_id")})},
                )
            else:
                merged[f.entry_id] = f
        return sort_flags(merged.values())


class RarePairingRule(Rule):
    rule_id = "R-008"
    title = "Unusual account pairings"
    targets = ("unusual_pairing",)
    references = ("AU-C 240", "ISA 240")
    population_description = "All journal entries (debit/credit account pairs)."
    criterion_description = (
        "The entry contains a debit-account/credit-account pair that occurs "
        "in at most max_count entries across the whole population."
    )
    limitations = (
        "The pairing profile is learned from the same population it scores — "
        "population profiling for lead generation, with no train/test split "
        "and no lookahead claim. A flag means 'rare within this ledger', "
        "never 'anomalous against the world'.",
        "Small populations make every pairing rare; the rule refuses below "
        "its minimum population instead of flagging everything.",
    )

    def __init__(self, max_count: int = 1, min_population: int = 500):
        self.max_count = max_count
        self.min_population = min_population

    def params(self):
        return {"max_count": self.max_count, "min_population": self.min_population}

    def applicable(self, ledger):
        if len(ledger.entries) < self.min_population:
            return (
                False,
                f"population {len(ledger.entries)} below minimum "
                f"{self.min_population}; every pairing would look rare",
            )
        return True, ""

    @staticmethod
    def _pairs(entry):
        return [
            (d, c)
            for d in entry.debit_account_ids
            for c in entry.credit_account_ids
        ]

    def evaluate(self, ledger):
        ok, _ = self.applicable(ledger)
        if not ok:
            return []
        counts = {}
        for e in ledger.entries:
            for p in self._pairs(e):
                counts[p] = counts.get(p, 0) + 1
        flags = []
        for e in ledger.entries:
            rare = sorted(
                {p for p in self._pairs(e) if counts[p] <= self.max_count}
            )
            if rare:
                described = ", ".join(
                    f"DR {d} / CR {c} (seen {counts[(d, c)]}x in "
                    f"{len(ledger.entries)} entries)"
                    for d, c in rare
                )
                flags.append(
                    Flag(
                        self.rule_id,
                        e.entry_id,
                        f"Account pairing rare within this population: {described}",
                        {"pairs": [list(p) for p in rare]},
                    )
                )
        return sort_flags(flags)


class SelfApprovalRule(Rule):
    rule_id = "R-009"
    title = "Approval segregation of duties"
    targets = ("self_approval",)
    references = ("AU-C 240",)
    population_description = (
        "Journal entries requiring approval (manual GL source, or amount at "
        "or above the approval threshold)."
    )
    criterion_description = (
        "The approver is the preparer, or no approver is recorded."
    )
    limitations = (
        "Approval fields evidence workflow state, not the substance of the "
        "review performed.",
    )

    def __init__(self, threshold_cents: int = None):
        self.threshold_cents = threshold_cents

    def params(self):
        return {"threshold_cents": self.threshold_cents}

    def applicable(self, ledger):
        if _threshold(ledger, self.threshold_cents) is None:
            return False, "no approval threshold configured or in ledger metadata"
        return True, ""

    def population(self, ledger):
        threshold = _threshold(ledger, self.threshold_cents)
        if threshold is None:
            return []
        return [
            e
            for e in ledger.entries
            if e.source == "GL" or e.amount_cents >= threshold
        ]

    def evaluate(self, ledger):
        flags = []
        for e in self.population(ledger):
            if e.approver_id is None:
                rationale = (
                    f"Approval required (source {e.source}, amount "
                    f"{cents_to_str(e.amount_cents)}) but no approver recorded"
                )
                kind = "missing_approval"
            elif e.approver_id == e.preparer_id:
                rationale = (
                    f"Prepared and approved by the same user {e.preparer_id}"
                )
                kind = "self_approval"
            else:
                continue
            flags.append(Flag(self.rule_id, e.entry_id, rationale, {"kind": kind}))
        return sort_flags(flags)


class DuplicateRule(Rule):
    rule_id = "R-010"
    title = "Duplicate entries"
    targets = ("duplicate_pair",)
    references = ("AU-C 240",)
    population_description = "All journal entries."
    criterion_description = (
        "Two or more entries by the same preparer with identical line "
        "structure (accounts, sides, amounts) posted within the window."
    )
    limitations = (
        "Identity is judged on preparer and line structure; recurring "
        "identical postings (e.g. contractual charges) can legitimately "
        "repeat across periods, which the window bounds.",
    )

    def __init__(self, window_days: int = 7):
        self.window_days = window_days

    def params(self):
        return {"window_days": self.window_days}

    @staticmethod
    def _signature(entry):
        return (
            entry.preparer_id,
            tuple(
                sorted(
                    (l.account_id, l.debit_cents, l.credit_cents)
                    for l in entry.lines
                )
            ),
        )

    def evaluate(self, ledger):
        groups = {}
        for e in ledger.entries:
            groups.setdefault(self._signature(e), []).append(e)
        flags = []
        for _sig, members in sorted(groups.items(), key=lambda kv: kv[1][0].entry_id):
            if len(members) < 2:
                continue
            members.sort(key=lambda e: (e.posting_date, e.entry_id))
            for e in members:
                partners = [
                    o.entry_id
                    for o in members
                    if o.entry_id != e.entry_id
                    and abs((o.posting_date - e.posting_date).days)
                    <= self.window_days
                ]
                if partners:
                    flags.append(
                        Flag(
                            self.rule_id,
                            e.entry_id,
                            f"Identical accounts, amounts and preparer "
                            f"({e.preparer_id}) as {', '.join(sorted(partners))} "
                            f"within {self.window_days} days",
                            {"partners": sorted(partners)},
                        )
                    )
        return sort_flags(flags)


class NearDuplicateRule(Rule):
    rule_id = "R-011"
    title = "Near-duplicate entries (shifted resubmissions)"
    targets = ("near_duplicate",)
    references = ("AU-C 240",)
    population_description = "All journal entries."
    criterion_description = (
        "Two entries by the same preparer touch the same accounts within the "
        "window with amounts within tolerance but not equal, and either (a) "
        "their descriptions carry the same reference tokens (digit runs such "
        "as invoice or check numbers) — the resubmitted-document pattern — "
        "or (b) neither carries conflicting references and the wording is "
        "nearly identical without being identical. Differing reference "
        "tokens veto the pair: different documents legitimately produce "
        "similar wording."
    )
    limitations = (
        "This is a lexical screen keyed on reference tokens and wording "
        "(difflib) — a resubmission that renumbers the document and rewords "
        "the description is invisible to it, as is any semantic rewording "
        "with different accounts. Flags are candidates for inspection, not "
        "established resubmissions.",
        "Identical descriptions with different amounts and no references "
        "(e.g. repeated payments on account) are deliberately not flagged: "
        "at ledger scale that pattern is routine business, and a screen "
        "that flags it drowns its own signal. Pair screens are "
        "density-dependent; the report card measures the false-positive "
        "cost at the size under test.",
    )

    def __init__(self, window_days: int = 7, amount_tolerance: float = 0.01,
                 min_description_similarity: float = 0.9):
        self.window_days = window_days
        self.amount_tolerance = amount_tolerance
        self.min_description_similarity = min_description_similarity

    def params(self):
        return {
            "window_days": self.window_days,
            "amount_tolerance": self.amount_tolerance,
            "min_description_similarity": self.min_description_similarity,
        }

    @staticmethod
    def _reference_tokens(entry) -> tuple:
        """Digit runs in the description, excluding the entry's own account
        numbers: 'Reclassification 6300 to 6350' names accounts, not
        documents, and treating those as shared references would flag every
        same-pair reclass at ledger scale."""
        import re

        own_accounts = set(entry.account_ids)
        return tuple(
            sorted(
                t
                for t in re.findall(r"\d{3,}", entry.description)
                if t not in own_accounts
            )
        )

    def evaluate(self, ledger):
        groups = {}
        for e in ledger.entries:
            key = (e.preparer_id, e.account_ids)
            groups.setdefault(key, []).append(e)
        flagged = {}
        for _key, members in sorted(groups.items()):
            if len(members) < 2:
                continue
            members.sort(key=lambda e: (e.posting_date, e.entry_id))
            tokens = {m.entry_id: self._reference_tokens(m) for m in members}
            for i, a in enumerate(members):
                for b in members[i + 1 :]:
                    gap = (b.posting_date - a.posting_date).days
                    if gap > self.window_days:
                        break
                    lo, hi = sorted((a.amount_cents, b.amount_cents))
                    if lo == 0 or lo == hi:
                        continue  # equal amounts are R-010's exact-match territory
                    if (hi - lo) / lo > self.amount_tolerance:
                        continue
                    ta, tb = tokens[a.entry_id], tokens[b.entry_id]
                    if ta and tb and ta == tb:
                        basis = f"same reference tokens {', '.join(ta)}"
                    elif ta and tb and ta != tb:
                        continue  # different documents; similar wording is expected
                    else:
                        if a.description == b.description:
                            continue  # routine repeated activity, no references
                        similarity = SequenceMatcher(
                            None, a.description, b.description
                        ).ratio()
                        if similarity < self.min_description_similarity:
                            continue
                        basis = f"wording similarity {similarity:.2f} with no conflicting references"
                    for this, other in ((a, b), (b, a)):
                        if this.entry_id not in flagged:
                            flagged[this.entry_id] = Flag(
                                self.rule_id,
                                this.entry_id,
                                f"Possible shifted resubmission of "
                                f"{other.entry_id}: same accounts and preparer "
                                f"({this.preparer_id}), amounts "
                                f"{cents_to_str(a.amount_cents)} vs "
                                f"{cents_to_str(b.amount_cents)}, {gap} day(s) "
                                f"apart; {basis}",
                                {"partner": other.entry_id, "basis": basis},
                            )
        return sort_flags(flagged.values())
