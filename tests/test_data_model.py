"""Unit tests for the data_model module."""

import json
import unittest
from datetime import date

from data_model import WeatherRecord, parse_bbc_forecast


class TestWeatherRecord(unittest.TestCase):
    """Tests for the WeatherRecord Pydantic model."""
    
    def test_valid_record_creation(self):
        """Test creating a valid WeatherRecord."""
        record = WeatherRecord(
            local_date=date(2026, 4, 25),
            timeslot="14:00",
            location_id=2644577,
            temperature_c=12,
            feels_like_c=10,
            weather_type_text="Partly Cloudy",
            precipitation_percent=0,
            wind_speed_kph=9,
        )
        
        self.assertEqual(record.local_date, date(2026, 4, 25))
        self.assertEqual(record.timeslot, "14:00")
        self.assertEqual(record.temperature_c, 12)
        self.assertTrue(record.is_calm)  # Both precip and wind are 0
    
    def test_invalid_timeslot_format(self):
        """Test that invalid timeslot format raises validation error."""
        with self.assertRaises(ValueError):
            WeatherRecord(
                local_date=date(2026, 4, 25),
                timeslot="invalid",  # Not HH:MM
                location_id=2644577,
                temperature_c=12,
                feels_like_c=10,
                weather_type_text="Partly Cloudy",
                precipitation_percent=0,
                wind_speed_kph=9,
            )
    
    def test_is_calm_false_with_wind(self):
        """Test is_calm returns False when wind is present."""
        record = WeatherRecord(
            local_date=date(2026, 4, 25),
            timeslot="14:00",
            location_id=2644577,
            temperature_c=12,
            feels_like_c=10,
            weather_type_text="Partly Cloudy",
            precipitation_percent=0,
            wind_speed_kph=5,  # Wind present
        )
        
        self.assertFalse(record.is_calm)
    
    def test_is_calm_false_with_precip(self):
        """Test is_calm returns False when precipitation is present."""
        record = WeatherRecord(
            local_date=date(2026, 4, 25),
            timeslot="14:00",
            location_id=2644577,
            temperature_c=12,
            feels_like_c=10,
            weather_type_text="Light Rain Showers",
            precipitation_percent=10,  # Precip present
            wind_speed_kph=0,
        )
        
        self.assertFalse(record.is_calm)


class TestParseBbcForecast(unittest.TestCase):
    """Tests for parsing BBC API response."""
    
    def setUp(self):
        """Set up sample BBC API response structure."""
        self.sample_response = {
            "location": {
                "name": "Leven",
            },
            "forecasts": [
                {
                    "detailed": {
                        "reports": [
                            {
                                "localDate": "2026-04-25",
                                "timeslot": "14:00",
                                "temperatureC": 12,
                                "feelsLikeTemperatureC": 10,
                                "weatherTypeText": "Partly Cloudy",
                                "enhancedWeatherDescription": "Partly cloudy and light winds",
                                "precipitationProbabilityInPercent": 0,
                                "precipitationProbabilityText": "Precipitation is not expected",
                                "windSpeedKph": 9,
                                "windDirection": "E",
                                "humidity": 70,
                            },
                            {
                                "localDate": "2026-04-25",
                                "timeslot": "15:00",
                                "temperatureC": 13,
                                "feelsLikeTemperatureC": 11,
                                "weatherTypeText": "Sunny Intervals",
                                "enhancedWeatherDescription": "Sunny intervals and light winds",
                                "precipitationProbabilityInPercent": 0,
                                "precipitationProbabilityText": "Precipitation is not expected",
                                "windSpeedKph": 8,
                                "windDirection": "E",
                                "humidity": 68,
                            },
                        ]
                    }
                }
            ]
        }
    
    def test_parse_sample_response(self):
        """Test parsing a complete sample response."""
        records = parse_bbc_forecast(self.sample_response, 2644577)
        
        self.assertEqual(len(records), 2)
        
        # Check first record
        self.assertEqual(records[0].local_date, date(2026, 4, 25))
        self.assertEqual(records[0].timeslot, "14:00")
        self.assertEqual(records[0].temperature_c, 12)
        self.assertEqual(records[0].location_name, "Leven")
    
    def test_parse_empty_forecasts(self):
        """Test parsing response with empty forecasts."""
        response = {"forecasts": []}
        
        with self.assertRaises(KeyError):
            parse_bbc_forecast(response, 2644577)
    
    def test_parse_missing_forecasts_key(self):
        """Test parsing response missing forecasts key."""
        response = {"location": {"name": "Test"}}
        
        with self.assertRaises(KeyError):
            parse_bbc_forecast(response, 2644577)
    
    def test_parse_skips_malformed_records(self):
        """Test that malformed records are skipped gracefully."""
        response = {
            "forecasts": [
                {
                    "detailed": {
                        "reports": [
                            {
                                "localDate": "2026-04-25",
                                "timeslot": "14:00",
                                "temperatureC": 12,
                                "feelsLikeTemperatureC": 10,
                                "weatherTypeText": "Partly Cloudy",
                                "precipitationProbabilityInPercent": 0,
                                "windSpeedKph": 9,
                            },
                            {
                                # Missing required fields
                                "localDate": "2026-04-25",
                                "timeslot": "15:00",
                            },
                        ]
                    }
                }
            ]
        }
        
        # Should skip the malformed record and keep the valid one
        records = parse_bbc_forecast(response, 2644577)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].timeslot, "14:00")


if __name__ == "__main__":
    unittest.main()