import unittest
from datetime import date

from core.dates import (
    add_business_days,
    business_days,
    first_business_day,
    holidays_for_range,
    is_business_day,
    last_business_day,
    last_n_business_days,
    month_last_day,
    nth_weekday,
    observed_holidays,
    period_str,
    us_federal_holidays,
)


class HolidayTests(unittest.TestCase):
    def test_2025_computed_holidays(self):
        h = us_federal_holidays(2025)
        for expected in (
            date(2025, 1, 1),
            date(2025, 1, 20),   # MLK: 3rd Monday of January
            date(2025, 2, 17),
            date(2025, 5, 26),   # Memorial: last Monday of May
            date(2025, 6, 19),
            date(2025, 7, 4),
            date(2025, 9, 1),
            date(2025, 10, 13),
            date(2025, 11, 11),
            date(2025, 11, 27),  # Thanksgiving: 4th Thursday of November
            date(2025, 12, 25),
        ):
            self.assertIn(expected, h)
        self.assertEqual(len(h), 11)

    def test_saturday_holiday_observed_friday(self):
        # July 4, 2026 falls on a Saturday; observed Friday July 3.
        h = observed_holidays(2026)
        self.assertIn(date(2026, 7, 3), h)
        self.assertNotIn(date(2026, 7, 4), h)

    def test_range_padding_covers_boundary_observance(self):
        # Jan 1, 2028 is a Saturday, observed Dec 31, 2027.
        h = holidays_for_range(date(2027, 12, 1), date(2027, 12, 31))
        self.assertIn(date(2027, 12, 31), h)


class BusinessDayTests(unittest.TestCase):
    def setUp(self):
        self.h = holidays_for_range(date(2025, 1, 1), date(2025, 12, 31))

    def test_january_2025_has_21_business_days(self):
        days = business_days(date(2025, 1, 1), date(2025, 1, 31), self.h)
        self.assertEqual(len(days), 21)  # 31 days − 8 weekend − Jan 1 − MLK

    def test_weekend_and_holiday_excluded(self):
        self.assertFalse(is_business_day(date(2025, 1, 4), self.h))  # Saturday
        self.assertFalse(is_business_day(date(2025, 1, 1), self.h))  # holiday
        self.assertTrue(is_business_day(date(2025, 1, 2), self.h))

    def test_add_business_days_skips_weekend(self):
        self.assertEqual(
            add_business_days(date(2025, 1, 3), 1, self.h), date(2025, 1, 6)
        )
        self.assertEqual(
            add_business_days(date(2025, 1, 6), -1, self.h), date(2025, 1, 3)
        )

    def test_first_last_business_day(self):
        self.assertEqual(first_business_day(2025, 1, self.h), date(2025, 1, 2))
        self.assertEqual(last_business_day(2025, 8, self.h), date(2025, 8, 29))

    def test_last_n_business_days_of_fy2025(self):
        window = last_n_business_days(date(2025, 12, 31), 5, self.h)
        self.assertEqual(
            window,
            frozenset(
                [
                    date(2025, 12, 24),
                    date(2025, 12, 26),
                    date(2025, 12, 29),
                    date(2025, 12, 30),
                    date(2025, 12, 31),
                ]
            ),
        )

    def test_month_last_day_and_period(self):
        self.assertEqual(month_last_day(2025, 2), date(2025, 2, 28))
        self.assertEqual(period_str(date(2025, 3, 7)), "2025-03")

    def test_nth_weekday_overflow_raises(self):
        with self.assertRaises(ValueError):
            nth_weekday(2025, 2, 0, 5)  # no 5th Monday in Feb 2025


if __name__ == "__main__":
    unittest.main()
