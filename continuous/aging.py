"""Exception aging: how long each lead has been sitting there.

A monitoring programme that only ever reports "this month's exceptions"
hides its worst problem — the leads nobody worked. Aging is the schedule
that makes them visible: every exception is filed under the monthly batch it
first appeared in, and aged in whole periods against a reporting period.

What this cannot say, and says so instead of implying otherwise: nothing
here knows whether an exception was *dispositioned*. This lab has flags and
a ledger; it has no follow-up records, no clearing dates, no auditor sign-
off. So the schedule ages every exception raised, and an organisation with
disposition tracking would age only the undispositioned ones. Calling the
result an "open items" schedule would be a claim the data cannot support
(DECISIONS D-031).

Age is measured in whole monthly periods, not days, because the batch is the
unit of the programme: an exception in the batch just processed is age 0
whatever day it posted. Entries posted after the reporting period are not
aged at all — a monitor running as of that period has not seen them yet —
and their count is reported separately rather than folded into a bucket.
"""

from dataclasses import dataclass

from continuous.periods import period_of

# Bucket edges in whole periods; the last bucket is open-ended.
DEFAULT_BUCKETS = (0, 1, 2, 3)

MAX_OLDEST_ROWS = 25


def months_between(earlier: str, later: str) -> int:
    """Whole months from one 'YYYY-MM' label to another; may be negative."""
    ey, em = int(earlier[:4]), int(earlier[5:7])
    ly, lm = int(later[:4]), int(later[5:7])
    return (ly - ey) * 12 + (lm - em)


def bucket_label(age: int, buckets=DEFAULT_BUCKETS) -> str:
    """'0', '1', '2', '3+' for the default edges — the open-ended top bucket
    is what stops a long tail from disappearing into a rounding."""
    edges = tuple(buckets)
    if age >= edges[-1]:
        return f"{edges[-1]}+"
    return str(age)


def bucket_labels(buckets=DEFAULT_BUCKETS) -> tuple:
    edges = tuple(buckets)
    return tuple(str(e) for e in edges[:-1]) + (f"{edges[-1]}+",)


@dataclass(frozen=True)
class AgedException:
    rule_id: str
    entry_id: str
    first_seen_period: str
    age_periods: int
    bucket: str

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "entry_id": self.entry_id,
            "first_seen_period": self.first_seen_period,
            "age_periods": self.age_periods,
            "bucket": self.bucket,
        }


@dataclass(frozen=True)
class AgingSchedule:
    as_of_period: str
    buckets: tuple
    aged: tuple
    by_bucket: dict            # bucket -> count
    by_rule: dict              # rule_id -> {bucket: count}
    n_not_yet_posted: int
    max_age_periods: int

    @property
    def n_exceptions(self) -> int:
        return len(self.aged)

    def oldest(self, limit: int = MAX_OLDEST_ROWS) -> tuple:
        """Oldest first; ties broken by rule then entry so the list is
        stable across runs."""
        return tuple(
            sorted(
                self.aged,
                key=lambda a: (-a.age_periods, a.rule_id, a.entry_id),
            )[:limit]
        )

    def to_dict(self) -> dict:
        return {
            "as_of_period": self.as_of_period,
            "buckets": list(self.buckets),
            "n_exceptions": self.n_exceptions,
            "n_not_yet_posted": self.n_not_yet_posted,
            "max_age_periods": self.max_age_periods,
            "by_bucket": dict(sorted(self.by_bucket.items())),
            "by_rule": {
                rid: dict(sorted(counts.items()))
                for rid, counts in sorted(self.by_rule.items())
            },
            "oldest": [a.to_dict() for a in self.oldest()],
            "basis": (
                "age in whole monthly batches between the batch an exception "
                "first appeared in and the reporting period; no disposition "
                "data exists, so every exception raised is aged"
            ),
        }


def flatten_flags(results) -> list:
    """All flags from a `rules.registry.evaluate_all` result, ordered."""
    out = []
    for rid in sorted(results):
        out.extend(results[rid]["flags"])
    return out


def age_exceptions(flags, ledger, as_of_period: str = None,
                   buckets=DEFAULT_BUCKETS) -> AgingSchedule:
    """Age flags against a reporting period (default: the ledger's last).

    One flag per (rule, entry) is aged; a rule that raises the same entry
    twice would be double-counted, and rules here do not.
    """
    periods = sorted({period_of(e) for e in ledger.entries})
    if as_of_period is None:
        as_of_period = periods[-1] if periods else ""
    if not as_of_period:
        raise ValueError("an as-of period is required for an empty ledger")

    labels = bucket_labels(buckets)
    by_bucket = {label: 0 for label in labels}
    by_rule = {}
    aged = []
    not_yet = 0
    max_age = 0
    for flag in sorted(flags, key=lambda f: (f.rule_id, f.entry_id)):
        first_seen = period_of(ledger.entry(flag.entry_id))
        age = months_between(first_seen, as_of_period)
        if age < 0:
            # Posted after the reporting period: a monitor run as of that
            # period has not seen this entry, so it has no age yet.
            not_yet += 1
            continue
        label = bucket_label(age, buckets)
        aged.append(
            AgedException(
                rule_id=flag.rule_id,
                entry_id=flag.entry_id,
                first_seen_period=first_seen,
                age_periods=age,
                bucket=label,
            )
        )
        by_bucket[label] += 1
        by_rule.setdefault(flag.rule_id, {l: 0 for l in labels})[label] += 1
        max_age = max(max_age, age)

    return AgingSchedule(
        as_of_period=as_of_period,
        buckets=labels,
        aged=tuple(aged),
        by_bucket=by_bucket,
        by_rule=by_rule,
        n_not_yet_posted=not_yet,
        max_age_periods=max_age,
    )
