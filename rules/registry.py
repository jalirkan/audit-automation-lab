"""Rule registry: the default battery and id-based lookup.

The battery is data-driven and explicit (suite files arrive with the CLI,
per toolkit D-019's suites-as-data discipline); a typo'd rule id fails
immediately with the list of valid ids.

Three batteries, not one. `default_rules()` is the point-in-time
journal-entry battery: eleven rules that examine one extract. The
continuous battery is separate because its rules need several monthly
batches and a baseline period to mean anything. The accounts-payable
battery is separate because it reads a subledger's document fields, which a
general-ledger extract does not have at all. In every case a report card
must grade a battery against the classes that battery was designed for
(DECISIONS D-030, D-033). All of them are reachable by id through
`build_rules`.
"""

from rules.ap import DuplicateInvoiceAmountDateRule, DuplicateInvoiceReferenceRule
from rules.drift import ProfileDriftRule
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

_RULE_CLASSES = (
    UnbalancedEntryRule,
    PeriodEndPostingRule,
    WeekendHolidayRule,
    RoundDollarRule,
    BelowThresholdRule,
    ShortDescriptionRule,
    DormantAccountRule,
    RarePairingRule,
    SelfApprovalRule,
    DuplicateRule,
    NearDuplicateRule,
)

_CONTINUOUS_RULE_CLASSES = (ProfileDriftRule,)

_AP_RULE_CLASSES = (
    DuplicateInvoiceReferenceRule,
    DuplicateInvoiceAmountDateRule,
)


def default_rules() -> list:
    """The point-in-time battery with default parameters, ordered by id."""
    rules = [cls() for cls in _RULE_CLASSES]
    return sorted(rules, key=lambda r: r.rule_id)


def continuous_rules() -> list:
    """The continuous-mode battery: rules that read a ledger as a sequence
    of monthly batches against a baseline period.

    Kept apart from `default_rules()` on purpose. Grading drift with the
    point-in-time battery mixed in would let an unrelated screen — a
    period-end selection sweeping a December plant, say — claim a drift
    detection it did nothing to earn, and the report card's recall would
    stop being a statement about the drift screen (DECISIONS D-030).
    """
    rules = [cls() for cls in _CONTINUOUS_RULE_CLASSES]
    return sorted(rules, key=lambda r: r.rule_id)


def ap_rules() -> list:
    """The accounts-payable battery: duplicate-invoice screens over a
    subledger extract.

    Kept apart from `default_rules()` for the reason recorded in D-030 and
    applied again in D-033: these rules key on document fields (vendor,
    reference, invoice date) that a general ledger does not carry, so they
    refuse to run on one — and grading them alongside the GL battery would
    credit AP recall to screens that read none of those fields.
    """
    rules = [cls() for cls in _AP_RULE_CLASSES]
    return sorted(rules, key=lambda r: r.rule_id)


def rule_class_by_id() -> dict:
    """Every rule in any battery, by id — so a subset can be built by id
    without knowing which battery a rule belongs to."""
    return {
        cls.rule_id: cls
        for cls in _RULE_CLASSES + _CONTINUOUS_RULE_CLASSES + _AP_RULE_CLASSES
    }


def build_rules(rule_ids=None) -> list:
    """Instantiate a subset by id; unknown ids fail loudly with the valid list."""
    classes = rule_class_by_id()
    if rule_ids is None:
        return default_rules()
    out = []
    for rid in rule_ids:
        if rid not in classes:
            raise ValueError(
                f"unknown rule id {rid!r}; valid ids: {', '.join(sorted(classes))}"
            )
        out.append(classes[rid]())
    return sorted(out, key=lambda r: r.rule_id)


def evaluate_all(ledger, rules=None) -> dict:
    """Run a battery. Returns {rule_id: {"applicable": bool, "reason": str,
    "population_size": int, "flags": [Flag, ...]}} — inapplicable rules
    report why and produce no flags (they are rendered as inconclusive
    procedures, never passes)."""
    results = {}
    for rule in default_rules() if rules is None else rules:
        ok, reason = rule.applicable(ledger)
        results[rule.rule_id] = {
            "rule": rule,
            "applicable": ok,
            "reason": reason,
            "population_size": rule.population_size(ledger) if ok else 0,
            "flags": rule.evaluate(ledger) if ok else [],
        }
    return results
