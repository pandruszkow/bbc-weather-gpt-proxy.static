"""Batch generator for weather forecast output files.

Slices unified weather records by temporal windows and generates
Markdown output files with formatted forecasts.
"""

import logging
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Callable, Optional

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


def calculate_window_dates(run_datetime: datetime) -> dict[str, tuple[date, date]]:
    """Calculate date ranges for each window based on run time.
    
    The 06:00 cutoff affects how many additional days are included:
    - Before/on 06:00: minimum additional days
    - After 06:00: maximum additional days
    
    Args:
        run_datetime: When the script is running
        
    Returns:
        Dict mapping window name to (start_date, end_date) inclusive tuples
    """
    run_date = run_datetime.date()
    run_time = run_datetime.time()
    cutoff_time = time(6, 0)
    
    # Determine if we're before or after cutoff
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
    
    # Group by date
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
    
    # Create staging directory for atomic writes
    location_name = None
    if records:
        location_name = records[0].location_name
    
    # Build location directory path
    location_dir_name = f"BBC Weather location {location_id}"
    location_dir = output_dir / location_dir_name
    
    # Calculate window date ranges
    windows = calculate_window_dates(run_datetime)
    
    written_files = []
    
    for window_name, (start_date, end_date) in windows.items():
        # Filter records for this window
        window_records = filter_records_by_date_range(records, start_date, end_date)
        
        # Verify we have complete coverage
        expected_days = (end_date - start_date).days + 1
        actual_days = len(set(r.local_date for r in window_records))
        
        if actual_days < expected_days:
            raise ValueError(
                f"Incomplete data for {window_name}: "
                f"expected {expected_days} days, got {actual_days}"
            )
        
        # Generate content
        content = generate_markdown_content(window_records, run_date, location_name)
        
        # Build filename
        # Format: "Weather forecast for yyyy-mm-dd (next {window}).md"
        filename = f"Weather forecast for {run_date.isoformat()} (next {window_name}).md"
        filepath = location_dir / filename
        
        # Write atomically
        write_file_atomic(filepath, content)
        written_files.append(filepath)
        
        logger.info(f"Generated {filepath} ({len(window_records)} records)")
    
    return written_files
