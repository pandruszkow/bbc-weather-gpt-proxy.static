# BBC Weather Batch Generator

Scrapes BBC Weather's unofficial JSON API and generates natural-language weather forecasts formatted for LLM consumption. Produces Markdown batch files with 24-hour, 3-day, and 1-week forecasts for multiple locations.

## Quick Start

### Prerequisites
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (for dependency management)

### Installation

```bash
# Clone and enter repository
cd repo/

# Bootstrap environment (checks for uv)
make

# Run for Leven, Scotland (location ID 2644577)
WEATHER_BATCH_LOCATION="2644577" make run
```

### Usage

```bash
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
| `batch_generator.py` | Temporal window slicing (24h/3d/1w). Markdown section generation. Atomic per-location writes. |
| `output_writer.py` | Atomic file persistence via temp+rename pattern. |
| `main.py` | CLI, threading orchestration (one thread per location), exit codes. |

See `adr/001-architecture.md` for detailed design rationale.

## Output Format

Generated files: `output/BBC Weather location {id}/Weather forecast for yyyy-mm-dd (next {window}).md`

Example content:

```markdown
## Today, 26th of April (Sunday)

Weather forecast for 2026-04-26 at noon: Temperature will be 11°C (feels like 11°C). No precipitation expected, with winds at 6 km/h. Expect sunny intervals.
Weather forecast for 2026-04-26 at 13:00h: Temperature will be 12°C (feels like 12°C). No precipitation expected, with winds at 7 km/h. Expect sunny intervals.

## Tomorrow, 27th of April (Monday)

Weather forecast for 2026-04-27 at 00:00h: Temperature will be 8°C (feels like 8°C). A 42% chance of precipitation, with winds at 11 km/h. Expect light rain showers.
```

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `WEATHER_BATCH_LOCATION` | Comma/semicolon/space-separated location IDs | (required for `make run`) |
| `WEATHER_BATCH_OUTPUT` | Output directory | `output/` |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Generic error |
| 10+N | N locations failed (capped at 100) |
| 126 | `uv`/`uvx` not executable |
| 127 | `uv`/`uvx` not found |

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

Unit tests use `unittest`. Fixture tests validate cached BBC API response structure:

```bash
python -m unittest discover -s tests -v
```

## API Source

Data from BBC Weather's unofficial JSON endpoint:
`https://weather-broker-cdn.api.bbci.co.uk/en/forecast/aggregated/{location_id}`

## License

See repository for license information.
