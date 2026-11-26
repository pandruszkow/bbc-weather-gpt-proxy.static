"""Main entrypoint and CLI for the BBC Weather batch generator.

Orchestrates the full pipeline: fetching, parsing, formatting, and writing
forecast data for multiple locations with parallel processing.
"""

import argparse
import logging
import os
import re
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from api_client import fetch_weather_data
from batch_generator import DEFAULT_LOCATIONS_PATH, generate_batch_files, get_uk_time, load_location_names
from data_model import parse_bbc_forecast, parse_bbc_issue_times

# Default configuration
DEFAULT_OUTPUT_DIR = Path("output")
ENV_VAR_OUTPUT = "WEATHER_BATCH_OUTPUT"
ENV_VAR_LOCATIONS = "WEATHER_BATCH_LOCATION"

# Exit codes
EXIT_SUCCESS = 0
EXIT_GENERIC_ERROR = 1
EXIT_BASE_FAILURE = 10  # 10 + count of failed locations

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_location_ids(value: str) -> list[int]:
    """Parse location IDs from a string.
    
    Supports separators: comma, semicolon, space
    
    Args:
        value: String containing location IDs
        
    Returns:
        List of integer location IDs
        
    Raises:
        ValueError: If parsing fails
    """
    # Split by comma, semicolon, or whitespace
    parts = re.split(r'[,;\s]+', value.strip())
    
    location_ids = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        try:
            location_ids.append(int(part))
        except ValueError:
            raise ValueError(f"Invalid location ID: '{part}'")
    
    return location_ids


def get_output_directory(cli_arg: Optional[str] = None) -> Path:
    """Determine output directory from env var or CLI arg.
    
    Priority: env var > CLI arg > default
    
    Args:
        cli_arg: Optional CLI-provided path
        
    Returns:
        Output directory path
    """
    # Check env var first (highest priority)
    env_value = os.environ.get(ENV_VAR_OUTPUT)
    if env_value:
        return Path(env_value)
    
    # Fall back to CLI arg
    if cli_arg:
        return Path(cli_arg)
    
    # Default
    return DEFAULT_OUTPUT_DIR


def process_single_location(
    location_id: int,
    output_dir: Path,
    run_datetime: datetime,
    location_name: Optional[str] = None,
) -> tuple[int, Optional[list[Path]]]:
    """Process a single location through the full pipeline.
    
    Args:
        location_id: BBC location identifier
        output_dir: Base output directory
        run_datetime: When the script is running
        location_name: Name from SUPPORTED_LOCATIONS.md (None: use the ID)
        
    Returns:
        Tuple of (location_id, list_of_written_files or None if failed)
    """
    try:
        logger.info(f"[{location_id}] Starting fetch")
        
        # Step 1: Fetch raw data
        raw_data = fetch_weather_data(location_id)
        logger.info(f"[{location_id}] Fetched {len(raw_data.get('forecasts', []))} forecast blocks")
        
        # Step 2: Parse into unified model
        records = parse_bbc_forecast(raw_data, location_id)
        logger.info(f"[{location_id}] Parsed {len(records)} hourly records")
        
        if not records:
            logger.warning(f"[{location_id}] No records parsed from response")
            return (location_id, None)
        
        # Step 3: Generate batch files
        issued_at, last_updated_at = parse_bbc_issue_times(raw_data)
        written_files = generate_batch_files(
            records,
            location_id,
            output_dir,
            run_datetime,
            location_name=location_name or str(location_id),
            issued_at=issued_at,
            last_updated_at=last_updated_at,
        )
        logger.info(f"[{location_id}] Generated {len(written_files)} batch files")
        
        return (location_id, written_files)
        
    except Exception as e:
        logger.error(f"[{location_id}] Failed: {e}")
        return (location_id, None)


def run_pipeline(
    location_ids: list[int],
    output_dir: Path,
) -> int:
    """Run the full pipeline for multiple locations.
    
    Spins up one thread per location for parallel processing.
    
    Args:
        location_ids: List of BBC location identifiers
        output_dir: Base output directory
        
    Returns:
        Exit code (0 for success, 10+N for N failures)
    """
    run_datetime = get_uk_time()
    location_names = load_location_names()
    
    logger.info(f"Starting pipeline for {len(location_ids)} location(s)")
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"Run datetime: {run_datetime.isoformat()}")
    
    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Process locations in parallel (one thread per location)
    results = {}
    threads = []
    
    def worker(location_id: int):
        result = process_single_location(
            location_id, output_dir, run_datetime, location_names.get(location_id)
        )
        results[location_id] = result[1]  # None or list of paths
    
    # Start threads
    for location_id in location_ids:
        t = threading.Thread(target=worker, args=(location_id,))
        t.start()
        threads.append(t)
    
    # Wait for all to complete
    for t in threads:
        t.join()
    
    # Calculate results
    successful = [lid for lid, files in results.items() if files is not None]
    failed = [lid for lid, files in results.items() if files is None]
    
    logger.info(f"Pipeline complete: {len(successful)} succeeded, {len(failed)} failed")
    
    if failed:
        logger.error(f"Failed locations: {failed}")
        return min(EXIT_BASE_FAILURE + len(failed), 100)
    
    return EXIT_SUCCESS


def main():
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Generate weather forecast batch files from BBC Weather API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Environment variables:
  {ENV_VAR_LOCATIONS}    Comma/semicolon/space separated location IDs
  {ENV_VAR_OUTPUT}       Override output directory (higher priority than --output)

With neither, every location in SUPPORTED_LOCATIONS.md (next to main.py) is used.

Examples:
  python main.py
  python main.py 2644577
  WEATHER_BATCH_LOCATION="2644577 2653940" python main.py
  WEATHER_BATCH_OUTPUT=/var/weather python main.py 2644577
        """
    )
    
    parser.add_argument(
        "locations",
        nargs="*",
        help="BBC location ID(s) (can also use WEATHER_BATCH_LOCATION env var)"
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR}, override with {ENV_VAR_OUTPUT})"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Determine location IDs
    location_ids: list[int] = []
    
    # CLI args take precedence if provided
    if args.locations:
        for loc_str in args.locations:
            try:
                location_ids.append(int(loc_str))
            except ValueError:
                logger.error(f"Invalid location ID: '{loc_str}'")
                return EXIT_GENERIC_ERROR
    else:
        # Try env var
        env_locations = os.environ.get(ENV_VAR_LOCATIONS)
        if env_locations:
            try:
                location_ids = parse_location_ids(env_locations)
            except ValueError as e:
                logger.error(f"Failed to parse {ENV_VAR_LOCATIONS}: {e}")
                return EXIT_GENERIC_ERROR
        else:
            # Fall back to SUPPORTED_LOCATIONS.md next to the code
            if not DEFAULT_LOCATIONS_PATH.exists():
                logger.error(f"No locations specified and {DEFAULT_LOCATIONS_PATH} not found.")
                logger.error(f"Use CLI args, {ENV_VAR_LOCATIONS} env var, or create {DEFAULT_LOCATIONS_PATH}.")
                return EXIT_GENERIC_ERROR
            logger.info(f"Reading locations from {DEFAULT_LOCATIONS_PATH}")
            location_ids = list(load_location_names())
    
    if not location_ids:
        logger.error(f"No locations specified. Use CLI args, {ENV_VAR_LOCATIONS} env var, or {DEFAULT_LOCATIONS_PATH.name}.")
        return EXIT_GENERIC_ERROR
    
    # Determine output directory
    output_dir = get_output_directory(args.output)
    
    # Run pipeline
    return run_pipeline(location_ids, output_dir)


if __name__ == "__main__":
    sys.exit(main())
