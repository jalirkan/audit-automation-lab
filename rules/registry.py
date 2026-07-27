"""Rule registry: the default battery and id-based lookup.

The battery is data-driven and explicit (suite files arrive with the CLI,
per toolkit D-019's suites-as-data discipline); a typo'd rule id fails
immediately with the list of valid ids.
"""

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


def default_rules() -> list:
    """The full battery with default parameters, ordered by rule id."""
    rules = [cls() for cls in _RULE_CLASSES]
    return sorted(rules, key=lambda r: r.rule_id)


def rule_class_by_id() -> dict:
    return {cls.rule_id: cls for cls in _RULE_CLASSES}


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
