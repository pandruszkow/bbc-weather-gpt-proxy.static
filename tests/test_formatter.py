"""Unit tests for the formatter module."""

import unittest
from datetime import date

from data_model import WeatherRecord
from formatter import (
    format_record,
    conditioned_timeslot,
    conditions_phrase,
    condition_weather_type,
    format_date_header,
)


class TestConditionedTimeslot(unittest.TestCase):
    """Tests for the conditioned_timeslot helper."""
    
    def test_noon_conversion(self):
        """12:00 should become 'noon'."""
        self.assertEqual(conditioned_timeslot("12:00"), "noon")
    
    def test_midnight_gets_h_suffix(self):
        """00:00 should become '00:00h'."""
        self.assertEqual(conditioned_timeslot("00:00"), "00:00h")
    
    def test_regular_time_gets_h_suffix(self):
        """Regular times should get 'h' suffix."""
        self.assertEqual(conditioned_timeslot("14:30"), "14:30h")
        self.assertEqual(conditioned_timeslot("23:00"), "23:00h")


class TestConditionsPhrase(unittest.TestCase):
    """Tests for the conditions_phrase helper."""
    
    def test_both_zero(self):
        """Both zero should return combined calm phrase."""
        result = conditions_phrase(0, 0)
        self.assertEqual(result, "No winds or precipitation expected.")
    
    def test_precip_zero_wind_nonzero(self):
        """Zero precip with wind should mention wind only."""
        result = conditions_phrase(0, 9)
        self.assertEqual(result, "No precipitation expected, with winds at 9 km/h.")
    
    def test_precip_nonzero_wind_zero(self):
        """Precip with zero wind should mention no wind."""
        result = conditions_phrase(10, 0)
        self.assertEqual(result, "A 10% chance of precipitation, with no wind expected.")
    
    def test_both_nonzero(self):
        """Both nonzero should mention both."""
        result = conditions_phrase(45, 12)
        self.assertEqual(result, "A 45% chance of precipitation, with winds at 12 km/h.")


class TestConditionWeatherType(unittest.TestCase):
    """Tests for the condition_weather_type helper."""
    
    def test_known_mappings(self):
        """Known weather types should use mapped values."""
        self.assertEqual(condition_weather_type("Partly Cloudy"), "partly cloudy")
        self.assertEqual(condition_weather_type("Clear Sky"), "clear skies")
        self.assertEqual(condition_weather_type("Light Rain Showers"), "light rain showers")
    
    def test_unknown_fallback_lowercase(self):
        """Unknown weather types should fall back to lowercase."""
        self.assertEqual(condition_weather_type("Heavy Snow"), "heavy snow")
        self.assertEqual(condition_weather_type("Thundery Showers"), "thundery showers")


class TestFormatDateHeader(unittest.TestCase):
    """Tests for the format_date_header helper."""
    
    def test_today_prefix(self):
        """Same date as run_date should get 'Today,' prefix."""
        run_date = date(2026, 4, 25)
        target_date = date(2026, 4, 25)
        result = format_date_header(target_date, run_date)
        self.assertTrue(result.startswith("Today,"))
        self.assertIn("25th of April", result)
        self.assertIn("(Saturday)", result)
    
    def test_tomorrow_prefix(self):
        """Next day should get 'Tomorrow,' prefix."""
        run_date = date(2026, 4, 25)
        target_date = date(2026, 4, 26)
        result = format_date_header(target_date, run_date)
        self.assertTrue(result.startswith("Tomorrow,"))
    
    def test_no_prefix_for_future_dates(self):
        """Dates beyond tomorrow should have no prefix."""
        run_date = date(2026, 4, 25)
        target_date = date(2026, 4, 27)
        result = format_date_header(target_date, run_date)
        self.assertFalse(result.startswith("Today,"))
        self.assertFalse(result.startswith("Tomorrow,"))
        self.assertIn("27th of April", result)
    
    def test_ordinal_suffixes(self):
        """Various day ordinals should be formatted correctly."""
        run_date = date(2026, 4, 1)
        
        # 1st, 2nd, 3rd
        self.assertIn("1st of April", format_date_header(date(2026, 4, 1), run_date))
        self.assertIn("2nd of April", format_date_header(date(2026, 4, 2), run_date))
        self.assertIn("3rd of April", format_date_header(date(2026, 4, 3), run_date))
        
        # 11th, 12th, 13th (special case)
        self.assertIn("11th of April", format_date_header(date(2026, 4, 11), run_date))
        self.assertIn("12th of April", format_date_header(date(2026, 4, 12), run_date))
        self.assertIn("13th of April", format_date_header(date(2026, 4, 13), run_date))
        
        # 21st, 22nd, 23rd
        self.assertIn("21st of April", format_date_header(date(2026, 4, 21), run_date))
        self.assertIn("22nd of April", format_date_header(date(2026, 4, 22), run_date))
        self.assertIn("23rd of April", format_date_header(date(2026, 4, 23), run_date))


class TestFormatRecord(unittest.TestCase):
    """Tests for the full format_record function."""
    
    def setUp(self):
        """Create sample weather records."""
        self.base_record = WeatherRecord(
            local_date=date(2026, 4, 25),
            timeslot="14:00",
            location_id=2644577,
            temperature_c=12,
            feels_like_c=10,
            weather_type_text="Partly Cloudy",
            precipitation_percent=0,
            wind_speed_kph=9,
        )
    
    def test_format_basic_record(self):
        """Test formatting a basic record."""
        result = format_record(self.base_record)
        
        # Should contain key elements
        self.assertIn("Weather forecast for 2026-04-25 at 14:00h", result)
        self.assertIn("Temperature will be 12°C (feels like 10°C)", result)
        self.assertIn("No precipitation expected, with winds at 9 km/h", result)
        self.assertIn("Expect partly cloudy", result)
    
    def test_format_noon_timeslot(self):
        """Test that noon is handled specially."""
        record = self.base_record.model_copy(update={"timeslot": "12:00"})
        result = format_record(record)
        
        self.assertIn("at noon", result)
        self.assertNotIn("12:00h", result)
    
    def test_format_calm_conditions(self):
        """Test formatting when both wind and precip are zero."""
        record = self.base_record.model_copy(update={"wind_speed_kph": 0})
        result = format_record(record)
        
        self.assertIn("No winds or precipitation expected", result)
    
    def test_format_with_precipitation(self):
        """Test formatting with non-zero precipitation."""
        record = self.base_record.model_copy(update={"precipitation_percent": 45})
        result = format_record(record)
        
        self.assertIn("A 45% chance of precipitation", result)


if __name__ == "__main__":
    unittest.main()