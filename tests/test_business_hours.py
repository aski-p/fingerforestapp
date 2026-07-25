import datetime as dt
import unittest

import fruit_auto


class BusinessDayScheduleTests(unittest.TestCase):
    def kst(self, year, month, day, hour, minute=0):
        return dt.datetime(year, month, day, hour, minute, tzinfo=fruit_auto.KST)

    def test_regular_weekday_during_working_hours_is_allowed(self):
        self.assertTrue(fruit_auto.is_business_hours(self.kst(2026, 7, 27, 10)))

    def test_weekend_during_working_hours_is_blocked(self):
        self.assertFalse(fruit_auto.is_business_hours(self.kst(2026, 7, 25, 10)))
        self.assertFalse(fruit_auto.is_business_hours(self.kst(2026, 7, 26, 10)))

    def test_public_holiday_during_working_hours_is_blocked(self):
        self.assertFalse(fruit_auto.is_business_hours(self.kst(2026, 8, 17, 10)))

    def test_friday_evening_defers_until_monday_morning(self):
        result = fruit_auto.next_business_start(self.kst(2026, 7, 24, 18, 30))
        expected = self.kst(2026, 7, 27, 9).astimezone(dt.timezone.utc)
        self.assertEqual(result, expected)

    def test_weekend_before_holiday_defers_until_next_working_day(self):
        result = fruit_auto.next_business_start(self.kst(2026, 8, 16, 10))
        expected = self.kst(2026, 8, 18, 9).astimezone(dt.timezone.utc)
        self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
