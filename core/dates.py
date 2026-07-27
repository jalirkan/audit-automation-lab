"""Business-day calendar utilities.

Holidays are computed algorithmically from the public statutory definitions
of US federal holidays (fixed dates and nth/last-weekday rules) — facts, not
copied tables. The default generator calendar is "weekdays minus observed US
federal holidays"; that choice is a modelling default, recorded in
DECISIONS.md, not a claim about any particular company.
"""

import calendar
from datetime import date, timedelta


def month_last_day(year: int, month: int) -> date:
    """Last calendar day of the month."""
    return date(year, month, calendar.monthrange(year, month)[1])


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """The n-th (1-based) given weekday (Mon=0) of a month."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    result = first + timedelta(days=offset + 7 * (n - 1))
    if result.month != month:
        raise ValueError(f"no {n}th weekday {weekday} in {year}-{month:02d}")
    return result


def last_weekday(year: int, month: int, weekday: int) -> date:
    """The last given weekday (Mon=0) of a month."""
    last = month_last_day(year, month)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def us_federal_holidays(year: int) -> frozenset:
    """Actual (unshifted) US federal holiday dates for a year."""
    return frozenset(
        [
            date(year, 1, 1),                # New Year's Day
            nth_weekday(year, 1, 0, 3),      # Birthday of Martin Luther King, Jr.
            nth_weekday(year, 2, 0, 3),      # Washington's Birthday
            last_weekday(year, 5, 0),        # Memorial Day
            date(year, 6, 19),               # Juneteenth
            date(year, 7, 4),                # Independence Day
            nth_weekday(year, 9, 0, 1),      # Labor Day
            nth_weekday(year, 10, 0, 2),     # Columbus Day
            date(year, 11, 11),              # Veterans Day
            nth_weekday(year, 11, 3, 4),     # Thanksgiving Day
            date(year, 12, 25),              # Christmas Day
        ]
    )


def observed_holidays(year: int) -> frozenset:
    """Observed dates: Saturday holidays shift to Friday, Sunday to Monday.

    Note a Saturday Jan 1 observes in the *prior* year; use
    holidays_for_range, which unions adjacent years, rather than calling this
    for a single year when working near year boundaries.
    """
    out = set()
    for h in us_federal_holidays(year):
        if h.weekday() == 5:
            out.add(h - timedelta(days=1))
        elif h.weekday() == 6:
            out.add(h + timedelta(days=1))
        else:
            out.add(h)
    return frozenset(out)


def holidays_for_range(start: date, end: date) -> frozenset:
    """Observed holidays covering [start, end], padded one year each side so
    observance shifts across year boundaries are never missed."""
    out = set()
    for year in range(start.year - 1, end.year + 2):
        out |= observed_holidays(year)
    return frozenset(out)


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def is_business_day(d: date, holidays: frozenset) -> bool:
    return d.weekday() < 5 and d not in holidays


def business_days(start: date, end: date, holidays: frozenset) -> list:
    """All business days in [start, end], ascending."""
    out = []
    cur = start
    one = timedelta(days=1)
    while cur <= end:
        if is_business_day(cur, holidays):
            out.append(cur)
        cur += one
    return out


def add_business_days(d: date, n: int, holidays: frozenset) -> date:
    """The date n business days after (n<0: before) d."""
    step = timedelta(days=1 if n >= 0 else -1)
    remaining = abs(n)
    cur = d
    while remaining > 0:
        cur += step
        if is_business_day(cur, holidays):
            remaining -= 1
    return cur


def first_business_day(year: int, month: int, holidays: frozenset) -> date:
    cur = date(year, month, 1)
    while not is_business_day(cur, holidays):
        cur += timedelta(days=1)
    return cur


def last_business_day(year: int, month: int, holidays: frozenset) -> date:
    cur = month_last_day(year, month)
    while not is_business_day(cur, holidays):
        cur -= timedelta(days=1)
    return cur


def last_n_business_days(end: date, n: int, holidays: frozenset) -> frozenset:
    """The n business days at or before *end* (walks back from end)."""
    out = []
    cur = end
    while len(out) < n:
        if is_business_day(cur, holidays):
            out.append(cur)
        cur -= timedelta(days=1)
    return frozenset(out)


def period_str(d: date) -> str:
    """Fiscal period label, calendar-month convention: 'YYYY-MM'."""
    return f"{d.year:04d}-{d.month:02d}"
