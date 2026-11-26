# BBC Weather Batch Generator

Scrapes BBC Weather's unofficial JSON API and generates natural-language weather forecasts formatted for LLM consumption. Produces Markdown batch files with 24-hour, 3-day, and 1-week forecasts for multiple locations.

Published every 2 hours by GitHub Actions (`.github/workflows/periodic-update.yml`) to https://pandruszkow.github.io/bbc-weather-gpt-proxy.static/ — e.g. `by-location/Edinburgh/next-3-days.md`.

## Quick Start

### Prerequisites
- Python 3.12+
- Either [uv](https://docs.astral.sh/uv/) (used by the Makefile) or plain `pip install -r requirements.txt` (used by CI)

### Usage

```bash
# All locations in SUPPORTED_LOCATIONS.md
make run            # or: python main.py

# Single location
WEATHER_BATCH_LOCATION="2644577" make run

# Multiple locations
WEATHER_BATCH_LOCATION="2644577,2653940,1234567" make run

# Custom output directory
WEATHER_BATCH_LOCATION="2644577" WEATHER_BATCH_OUTPUT=/var/weather make run

# Run directly without make (for development)
python main.py 2644577 2653940
```

## Architecture

Six-layer modular pipeline:

| Module | Responsibility |
|--------|---------------|
| `api_client.py` | HTTP I/O with BBC Weather API. Exponential backoff, 429 handling, 5 retries, 5min timeout. |
| `data_model.py` | Unified `WeatherRecord` Pydantic model. Decouples downstream logic from BBC-specific JSON structure. |
| `formatter.py` | One record → one sentence. Template-based with visible conditioning: `{conditions_phrase(precipitation_percent, wind_speed_kph)}`. |
| `batch_generator.py` | Temporal window slicing (24h/3d/1w). Markdown generation. Validates every window before writing any file. |
| `output_writer.py` | Atomic file persistence via temp+rename pattern. |
| `main.py` | CLI, threading orchestration (one thread per location), exit codes. |

See `adr/001-architecture.md` for detailed design rationale.

## Output Format

Each location is written twice, with identical content:

- `{output}/by-location/{name}/next-{24-hours,3-days,1-week}.md` — name from `SUPPORTED_LOCATIONS.md` (falls back to the ID for unlisted IDs)
- `{output}/by-location-id/{id}/next-{24-hours,3-days,1-week}.md`

`make_index_page.py` writes `{output}/index.html` linking the by-name files.

Example content:

```markdown
# Weather forecast data for Leven

Generated: Sunday 26 April 2026, 11:59 BST. BBC forecast issued: Sunday 26 April 2026, 10:47 BST; last updated: Sunday 26 April 2026, 11:31 BST. All times are UK local time.

## Today, 26th of April (Sunday)

Weather forecast for 2026-04-26 at noon: Temperature will be 11°C (feels like 11°C). No precipitation expected, with winds at 6 km/h. Expect sunny intervals.
Weather forecast for 2026-04-26 at 13:00h: Temperature will be 12°C (feels like 12°C). No precipitation expected, with winds at 7 km/h. Expect sunny intervals.

## Tomorrow, 27th of April (Monday)

Weather forecast for 2026-04-27 at 00:00h: Temperature will be 8°C (feels like 8°C). A 42% chance of precipitation, with winds at 11 km/h. Expect light rain showers.
```

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `WEATHER_BATCH_LOCATION` | Comma/semicolon/space-separated location IDs (CLI args take precedence) | every ID in `SUPPORTED_LOCATIONS.md` |
| `WEATHER_BATCH_OUTPUT` | Output directory (takes precedence over `--output`) | `output/` (CI: `_output/`) |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Generic error |
| 10+N | N locations failed (capped at 100) |

(`make` exits 127 if `uv` is missing; `main.py` itself never does.)

## Development

```bash
# Run tests
make test

# Install for system-wide use
make install

# Clean output and caches
make clean
```

## Testing

Unit tests use `unittest` and need no network. They run in CI on every push (`.github/workflows/tests.yml`), deliberately separate from the deploy workflow so a broken test can't freeze the feed.

```bash
python -m unittest discover -s tests -v
```

## API Source

Data from BBC Weather's unofficial JSON endpoint:
`https://weather-broker-cdn.api.bbci.co.uk/en/forecast/aggregated/{location_id}`

## License

See repository for license information.
