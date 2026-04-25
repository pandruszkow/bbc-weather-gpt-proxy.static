import json
import pathlib
import unittest
from datetime import date, timedelta

FIXTURE_DIR = pathlib.Path(__file__).parent.parent / "test_data"
FIXTURE_FILE = FIXTURE_DIR / "levenside_weather.json"


class TestLevensideWeatherFixture(unittest.TestCase):
    def test_fixture_file_exists(self):
        assert FIXTURE_FILE.exists(), f"Fixture not found: {FIXTURE_FILE}"

    def test_fixture_is_valid_json(self):
        with open(FIXTURE_FILE) as f:
            data = json.load(f)
        assert isinstance(data, dict)

    def test_fixture_has_expected_top_level_keys(self):
        with open(FIXTURE_FILE) as f:
            data = json.load(f)
        assert "forecasts" in data, "Missing 'forecasts' key"
        assert "location" in data, "Missing 'location' key"

    def test_fixture_location_name_is_levenside(self):
        with open(FIXTURE_FILE) as f:
            data = json.load(f)
        assert "name" in data["location"]
        assert "Leven" in data["location"]["name"], f"Expected Leven, got {data['location']['name']}"

    def test_fixture_has_forecast_data(self):
        with open(FIXTURE_FILE) as f:
            data = json.load(f)
        forecasts = data["forecasts"]
        assert isinstance(forecasts, list)
        assert len(forecasts) > 0, "Expected at least one forecast entry"

    def test_fixture_forecast_has_detailed_reports(self):
        with open(FIXTURE_FILE) as f:
            data = json.load(f)
        first = data["forecasts"][0]
        assert "detailed" in first, "Missing 'detailed' in first forecast"
        assert "reports" in first["detailed"], "Missing 'reports' in detailed"

    def test_fixture_reports_contain_required_fields(self):
        with open(FIXTURE_FILE) as f:
            data = json.load(f)
        reports = data["forecasts"][0]["detailed"]["reports"]
        assert len(reports) > 0
        r = reports[0]
        for field in ["localDate", "timeslot", "temperatureC", "enhancedWeatherDescription"]:
            assert field in r, f"Missing required field: {field}"

    def test_fixture_covers_today_plus_two_days(self):
        with open(FIXTURE_FILE) as f:
            data = json.load(f)
        dates = set()
        for fc in data["forecasts"]:
            for r in fc["detailed"]["reports"]:
                dates.add(r["localDate"])
        today = date.today()
        expected = {str(today + timedelta(days=i)) for i in range(3)}
        assert expected.issubset(dates), f"Expected dates {expected} not all present in {dates}"

    def test_fixture_covers_reasonable_temperature_range(self):
        with open(FIXTURE_FILE) as f:
            data = json.load(f)
        temps = []
        for fc in data["forecasts"]:
            for r in fc["detailed"]["reports"]:
                temps.append(r["temperatureC"])
        assert temps, "No temperature data found"
        assert all(-30 < t < 55 for t in temps), f"Temperature values out of range: {temps}"