"""Rule framework: Flag records and the Rule contract.

Standards are referenced by ID with original one-line summaries only
(no standard text is reproduced — same discipline as toolkit D-003/D-025).
"""

from dataclasses import dataclass, field

# Original one-line summaries, written for this project. Rules cite the IDs.
REFERENCES = {
    "AU-C 240": (
        "US GAAS standard on the auditor's consideration of fraud; directs "
        "testing of journal entries with emphasis on period-end and unusual "
        "items (original summary)."
    ),
    "ISA 240": (
        "International auditing standard on responsibilities relating to "
        "fraud; requires testing the appropriateness of journal entries and "
        "other adjustments (original summary)."
    ),
    "AU-C 530": (
        "US GAAS standard on audit sampling: designing samples and "
        "projecting results to populations (original summary)."
    ),
}


@dataclass(frozen=True)
class Flag:
    """One exception raised by one rule for one entry.

    `rationale` is specific to the entry (amounts, dates, counterparts) so a
    reviewer can evaluate the lead without re-deriving it. A flag directs
    attention; it concludes nothing.
    """

    rule_id: str
    entry_id: str
    rationale: str
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "entry_id": self.entry_id,
            "rationale": self.rationale,
            "details": self.details,
        }


class Rule:
    """Contract for a deterministic JE test.

    Class attributes are the workpaper-facing metadata; `evaluate` returns
    flags sorted by entry id. `applicable` lets a rule refuse to run
    (returning why) instead of producing meaningless output — the workpaper
    renders that as an inconclusive procedure, never as a pass.
    """

    rule_id = "R-000"
    title = ""
    targets = ()          # anomaly classes this rule is designed to catch
    references = ()       # keys into REFERENCES
    population_description = ""
    criterion_description = ""
    limitations = ()

    def params(self) -> dict:
        """JSONable parameter echo for the workpaper."""
        return {}

    def applicable(self, ledger):
        """(is_applicable, reason_if_not)."""
        return True, ""

    def population(self, ledger):
        """Entries this rule examines. Default: the full ledger —
        a complete examination of the configured population, not a sample
        (framing per toolkit D-031)."""
        return list(ledger.entries)

    def population_size(self, ledger) -> int:
        return len(self.population(ledger))

    def evaluate(self, ledger):
        raise NotImplementedError

    def describe(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "title": self.title,
            "targets": list(self.targets),
            "references": list(self.references),
            "population": self.population_description,
            "criterion": self.criterion_description,
            "limitations": list(self.limitations),
            "params": self.params(),
        }


def sort_flags(flags):
    return sorted(flags, key=lambda f: (f.entry_id, f.rule_id))
