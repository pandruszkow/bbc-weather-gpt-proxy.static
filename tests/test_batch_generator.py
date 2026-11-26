"""Unit tests for batch_generator: window validation, naming, provenance."""

import json
import pathlib
import tempfile
import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from batch_generator import (
    DEFAULT_LOCATIONS_PATH,
    format_provenance_line,
    generate_batch_files,
    load_location_names,
)
from data_model import parse_bbc_forecast, parse_bbc_issue_times

FIXTURE_FILE = pathlib.Path(__file__).parent.parent / "test_data" / "levenside_weather.json"
UK = ZoneInfo("Europe/London")
LEVEN = 2644577


def load_fixture() -> dict:
    with open(FIXTURE_FILE) as f:
        return json.load(f)


def day_headers(path: pathlib.Path) -> list[str]:
    return [line for line in path.read_text().splitlines() if line.startswith("## ")]


class TestLateEveningRun(unittest.TestCase):
    """Regression: from ~23:00 UK time BBC has no slots left for today.

    The strict 3d/1w day count used to demand today anyway, so every run
    between 23:00 and midnight failed for every location and the deploy was
    skipped (45 of 515 runs, Apr-Jul 2026).
    """

    def setUp(self):
        raw = load_fixture()
        # The fixture was captured at ~22:01 BST; its only slot for 25 April
        # is 23:00. A run at 23:17 would no longer see it.
        records = [
            r for r in parse_bbc_forecast(raw, LEVEN)
            if not (r.local_date == date(2026, 4, 25) and r.timeslot == "23:00")
        ]
        self.assertNotIn(date(2026, 4, 25), {r.local_date for r in records})
        self.records = records
        self.tmp = tempfile.TemporaryDirectory()
        self.out = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_generates_all_windows_after_23h(self):
        run = datetime(2026, 4, 25, 23, 17, tzinfo=UK)
        written = generate_batch_files(self.records, LEVEN, self.out, run, location_name="Leven")
        self.assertEqual(len(written), 6)

        three_day = day_headers(self.out / "by-location" / "Leven" / "next-3-days.md")
        self.assertEqual(len(three_day), 3)
        self.assertTrue(three_day[0].startswith("## Tomorrow, 26th of April"))

        one_week = day_headers(self.out / "by-location" / "Leven" / "next-1-week.md")
        self.assertEqual(len(one_week), 7)

        next_24h = day_headers(self.out / "by-location" / "Leven" / "next-24-hours.md")
        self.assertEqual(next_24h, ["## Tomorrow, 26th of April (Sunday)"])

    def test_gap_in_later_day_still_fails(self):
        """The exemption is for an empty *today* only; a missing future day is still an error."""
        records = [r for r in self.records if r.local_date != date(2026, 4, 27)]
        run = datetime(2026, 4, 25, 23, 17, tzinfo=UK)
        with self.assertRaisesRegex(ValueError, "Incomplete data for 3d"):
            generate_batch_files(records, LEVEN, self.out, run, location_name="Leven")

    def test_failed_validation_writes_nothing(self):
        records = [r for r in self.records if r.local_date != date(2026, 5, 1)]  # breaks 1w only
        run = datetime(2026, 4, 25, 23, 17, tzinfo=UK)
        with self.assertRaises(ValueError):
            generate_batch_files(records, LEVEN, self.out, run, location_name="Leven")
        self.assertEqual(list(self.out.rglob("*.md")), [])


class TestNormalRun(unittest.TestCase):
    def setUp(self):
        self.raw = load_fixture()
        self.records = parse_bbc_forecast(self.raw, LEVEN)
        self.tmp = tempfile.TemporaryDirectory()
        self.out = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_today_included_when_present(self):
        run = datetime(2026, 4, 25, 22, 30, tzinfo=UK)
        generate_batch_files(self.records, LEVEN, self.out, run, location_name="Leven")
        three_day = day_headers(self.out / "by-location" / "Leven" / "next-3-days.md")
        self.assertEqual(len(three_day), 4)
        self.assertTrue(three_day[0].startswith("## Today, 25th of April"))

    def test_name_lookup_independent_of_output_dir(self):
        """Output outside the repo must still resolve 'Leven', not '2644577'."""
        run = datetime(2026, 4, 25, 22, 30, tzinfo=UK)
        generate_batch_files(self.records, LEVEN, self.out, run)  # no location_name
        page = self.out / "by-location" / "Leven" / "next-24-hours.md"
        self.assertTrue(page.exists())
        self.assertTrue(page.read_text().startswith("# Weather forecast data for Leven\n"))
        self.assertTrue((self.out / "by-location-id" / str(LEVEN) / "next-24-hours.md").exists())

    def test_provenance_line_under_h1(self):
        run = datetime(2026, 4, 25, 22, 30, tzinfo=UK)
        issued, updated = parse_bbc_issue_times(self.raw)
        generate_batch_files(
            self.records, LEVEN, self.out, run,
            location_name="Leven", issued_at=issued, last_updated_at=updated,
        )
        lines = (self.out / "by-location" / "Leven" / "next-3-days.md").read_text().splitlines()
        self.assertEqual(lines[0], "# Weather forecast data for Leven")
        self.assertEqual(lines[1], "")
        self.assertEqual(
            lines[2],
            "Generated: Saturday 25 April 2026, 22:30 BST. "
            "BBC forecast issued: Saturday 25 April 2026, 10:47 BST; "
            "last updated: Saturday 25 April 2026, 22:01 BST. "
            "All times are UK local time.",
        )
        self.assertEqual(lines[3], "")
        self.assertTrue(lines[4].startswith("## Today, 25th of April"))


class TestProvenanceLine(unittest.TestCase):
    def test_utc_inputs_rendered_in_uk_time(self):
        gen = datetime(2026, 11, 26, 17, 10, tzinfo=UK)
        issued = datetime.fromisoformat("2026-11-26T16:01:56+00:00")
        updated = datetime.fromisoformat("2026-11-26T16:24:40.681+00:00")
        self.assertEqual(
            format_provenance_line(gen, issued, updated),
            "Generated: Thursday 26 November 2026, 17:10 GMT. "
            "BBC forecast issued: Thursday 26 November 2026, 16:01 GMT; "
            "last updated: Thursday 26 November 2026, 16:24 GMT. "
            "All times are UK local time.",
        )

    def test_missing_bbc_times(self):
        gen = datetime(2026, 11, 26, 17, 10, tzinfo=UK)
        self.assertEqual(
            format_provenance_line(gen),
            "Generated: Thursday 26 November 2026, 17:10 GMT. All times are UK local time.",
        )


class TestIssueTimes(unittest.TestCase):
    def test_parses_offset_and_z_suffix(self):
        issued, updated = parse_bbc_issue_times(
            {"issueDate": "2026-11-26T16:01:56+00:00", "lastUpdated": "2026-11-26T16:24:40.681Z"}
        )
        self.assertEqual(issued, datetime(2026, 11, 26, 16, 1, 56, tzinfo=ZoneInfo("UTC")))
        self.assertEqual(updated.utcoffset().total_seconds(), 0)
        self.assertEqual((updated.hour, updated.minute), (16, 24))

    def test_missing_or_garbage_is_none(self):
        self.assertEqual(parse_bbc_issue_times({}), (None, None))
        self.assertEqual(parse_bbc_issue_times({"issueDate": "soon", "lastUpdated": 5}), (None, None))
        self.assertEqual(parse_bbc_issue_times({"issueDate": "2026-11-26T16:01:56"}), (None, None))


class TestLoadLocationNames(unittest.TestCase):
    def test_repo_file(self):
        names = load_location_names()
        self.assertEqual(names[LEVEN], "Leven")
        self.assertEqual(names[2650225], "Edinburgh")

    def test_default_path_is_next_to_code(self):
        self.assertEqual(DEFAULT_LOCATIONS_PATH.parent, pathlib.Path(__file__).resolve().parent.parent)

    def test_parsing_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "SUPPORTED_LOCATIONS.md"
            path.write_text("<!-- comment: 1 -->\n\nAlpha: 1\n  Beta :2  \nbroken: x\nno colon\n")
            self.assertEqual(load_location_names(path), {1: "Alpha", 2: "Beta"})
            self.assertEqual(load_location_names(pathlib.Path(tmp) / "missing.md"), {})


if __name__ == "__main__":
    unittest.main()
