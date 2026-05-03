"""Batch generator for weather forecast output files.

Slices unified weather records by temporal windows and generates
Markdown output files with formatted forecasts.
"""

import logging
import os
import re
from datetime import date, datetime, time, timedelta
from collections import defaultdict
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from data_model import WeatherRecord
from formatter import format_record, format_date_header
from output_writer import write_file_atomic

logger = logging.getLogger(__name__)

# Window definitions: (name, days_after_today_before_0600, days_after_today_after_0600)
WINDOW_DEFINITIONS = [
    ("24h", 0, 1),  # Today only before 06:00, today+tomorrow after
    ("3d", 2, 3),   # Today+2 more before 06:00, today+3 more after
    ("1w", 6, 7),   # Today+6 more before 06:00, today+7 more after
]

# Filename for supported locations list
SUPPORTED_LOCATIONS_FILE = "SUPPORTED_LOCATIONS.md"


def load_location_names(repo_root: Path) -> dict[int, str]:
    """Load location ID to name mapping from SUPPORTED_LOCATIONS.md.
    
    Args:
        repo_root: Path to the repository root
        
    Returns:
        Dict mapping location_id (int) to location name (str)
    """
    locations_file = repo_root / SUPPORTED_LOCATIONS_FILE
    if not locations_file.exists():
        logger.warning(f"Supported locations file not found: {locations_file}")
        return {}
    
    mapping = {}
    content = locations_file.read_text()
    
    # Parse "CityName: location_id" lines, skipping the HTML comment
    for line in content.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('<!--'):
            continue
        if ':' in line:
            name, id_str = line.split(':', 1)
            try:
                mapping[int(id_str.strip())] = name.strip()
            except ValueError:
                logger.warning(f"Invalid location entry: {line}")
    
    logger.info(f"Loaded {len(mapping)} location names from {SUPPORTED_LOCATIONS_FILE}")
    return mapping


def get_uk_time() -> datetime:
    """Get current time in UK timezone (UTC+0 in winter, UTC+1 in summer)."""
    uk_tz = ZoneInfo("Europe/London")
    return datetime.now(uk_tz)


def calculate_window_dates(run_datetime: datetime) -> dict[str, tuple[date, date]]:
    """Calculate date ranges for each window based on run time.
    
    The 06:00 cutoff affects how many additional days are included.
    Time is evaluated in UK local time (handles GMT/BST automatically).
    
    Args:
        run_datetime: When the script is running (in UK local time)
        
    Returns:
        Dict mapping window name to (start_date, end_date) inclusive tuples
    """
    run_date = run_datetime.date()
    run_time = run_datetime.time()
    cutoff_time = time(6, 0)
    
    # Determine if we're before or after cutoff (in UK local time)
    after_cutoff = run_time > cutoff_time
    
    windows = {}
    for name, days_before, days_after in WINDOW_DEFINITIONS:
        days_additional = days_after if after_cutoff else days_before
        end_date = run_date + timedelta(days=days_additional)
        windows[name] = (run_date, end_date)
    
    return windows


def filter_records_by_date_range(
    records: list[WeatherRecord],
    start_date: date,
    end_date: date,
) -> list[WeatherRecord]:
    """Filter records to those within a date range (inclusive).
    
    Args:
        records: List of weather records
        start_date: Start of range (inclusive)
        end_date: End of range (inclusive)
        
    Returns:
        Filtered list of records
    """
    return [
        r for r in records
        if start_date <= r.local_date <= end_date
    ]


def group_records_by_date(records: list[WeatherRecord]) -> dict[date, list[WeatherRecord]]:
    """Group records by their local_date.
    
    Args:
        records: List of weather records
        
    Returns:
        Dict mapping date to list of records for that date
    """
    grouped = defaultdict(list)
    for record in records:
        grouped[record.local_date].append(record)
    
    # Sort records within each day by timeslot
    for date_key in grouped:
        grouped[date_key].sort(key=lambda r: r.timeslot)
    
    return dict(grouped)


def generate_markdown_content(
    records: list[WeatherRecord],
    run_date: date,
    location_name: Optional[str] = None,
) -> str:
    """Generate Markdown content from weather records.
    
    Creates sections per date with formatted forecast sentences.
    
    Args:
        records: Weather records to include
        run_date: The date the script was run (for relative date headers)
        location_name: Optional location name for header
        
    Returns:
        Complete Markdown document as string
    """
    if not records:
        return ""
    
    lines = []
    
    # Add H1 header with location name
    if location_name:
        lines.append(f"# Weather forecast data for {location_name}")
    else:
        lines.append("# Weather forecast data")
    
    lines.append("")
    by_date = group_records_by_date(records)
    
    for date_key in sorted(by_date.keys()):
        # Section header with relative prefix
        date_header = format_date_header(date_key, run_date)
        lines.append(f"## {date_header}")
        lines.append("")
        
        # Forecast sentences for this date
        for record in by_date[date_key]:
            sentence = format_record(record)
            lines.append(sentence)
        
        lines.append("")
    
    return "\n".join(lines)


def generate_batch_files(
    records: list[WeatherRecord],
    location_id: int,
    output_dir: Path,
    run_datetime: Optional[datetime] = None,
) -> list[Path]:
    """Generate all batch files for a location.
    
    Creates 24h, 3d, and 1w forecast files based on the current time.
    All files are written or none (atomic per-location).
    
    Args:
        records: All available weather records for the location
        location_id: BBC location identifier
        output_dir: Base output directory
        run_datetime: When the script is running (defaults to now)
        
    Returns:
        List of paths to written files
        
    Raises:
        ValueError: If insufficient data for any window
    """
    if run_datetime is None:
        run_datetime = datetime.now()
    
    run_date = run_datetime.date()
    
    # Load location name mapping
    location_names = load_location_names(output_dir.parent)
    
    # Determine location name (from mapping, or fallback to ID as string)
    location_name = location_names.get(location_id, str(location_id))
    
    # Build both directory paths:
    # - by-location/{location_name}/
    # - by-location-id/{location_id}/
    location_dir_by_name = output_dir / "by-location" / location_name
    location_dir_by_id = output_dir / "by-location-id" / str(location_id)
    
    # Calculate window date ranges
    windows = calculate_window_dates(run_datetime)
    
    written_files = []
    
    # Window name to filename mapping
    window_filename_map = {
        "24h": "next-24-hours.md",
        "3d": "next-3-days.md",
        "1w": "next-1-week.md",
    }
    
    for window_name, (start_date, end_date) in windows.items():
        # Filter records for this window
        window_records = filter_records_by_date_range(records, start_date, end_date)
        
        # Verify we have at least today for 24h (permissive - BBC may not have tomorrow yet)
        # For 3d and 1w, require complete coverage
        actual_days = len(set(r.local_date for r in window_records))
        
        if window_name == "24h":
            # Permissive: at minimum we need today
            if actual_days < 1:
                raise ValueError(
                    f"No data available for {window_name}: "
                    f"expected at least today's data"
                )
        else:
            # Strict validation for longer windows
            expected_days = (end_date - start_date).days + 1
            if actual_days < expected_days:
                raise ValueError(
                    f"Incomplete data for {window_name}: "
                    f"expected {expected_days} days, got {actual_days}"
                )
        
        # Generate content
        content = generate_markdown_content(window_records, run_date, location_name)
        
        # Build filename: next-{interval}.md
        filename = window_filename_map.get(window_name, f"next-{window_name}.md")
        
        # Write to both paths: by-location/{name} and by-location-id/{id}
        filepath_by_name = location_dir_by_name / filename
        filepath_by_id = location_dir_by_id / filename
        
        write_file_atomic(filepath_by_name, content)
        write_file_atomic(filepath_by_id, content)
        
        written_files.extend([filepath_by_name, filepath_by_id])
        
        logger.info(f"Generated {filepath_by_name} and {filepath_by_id} ({len(window_records)} records)")
    
    return written_files
    
    return written_files
