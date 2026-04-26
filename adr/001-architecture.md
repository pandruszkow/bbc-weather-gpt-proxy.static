# ADR 001: BBC Weather Batch Generator Architecture

## Status
Accepted

## Context
The BBC Weather scraper (originally 2024) needed modernization. The original `bbc-grabber.py` was monolithic, mixing HTTP fetching, JSON parsing, data transformation, and output generation. Key drivers for change:
- BBC API/HTML changes in 2026
- Need for resilience (transient failures, rate limits)
- Need for natural-language output suitable for LLMs (attire, laundry, rain decisions)
- Need to support multiple locations and temporal windows (24h / 3d / 1w)

Key requirements established through discussion:
1. **API resilience**: handle 429 with Retry-After, exponential backoff with jitter, 5 retries, 5-minute hard timeout per request
2. **Data model decoupling**: provider-agnostic `WeatherRecord` so new providers only require a new parser function
3. **Natural language output**: clear, LLM-friendly sentences; template makes conditioning visible: `{conditions_phrase(precipitation_percent, wind_speed_kph)}`
4. **Temporal windows**: 24h (with 06:00 cutoff), 3d (today + next 3 full days), 1w (today + next 7 full days)
5. **Multi-location**: parallel processing (classic one-thread-per-location)
6. **Atomic per-location writes**: all-or-nothing for a location; staged temp file + rename
7. **Operational clarity**: domain-specific exit codes (10+N for N failed locations), env-based config

## Decision
Adopt a **six-layer modular pipeline**:

1. **api_client.py** — HTTP I/O only. Exponential backoff with jitter; 429 → obey Retry-After; 5 retries; 5-minute hard timeout; detailed error logging with last-response dump.
2. **data_model.py** — Unified Pydantic `WeatherRecord`. BBC-specific parser `parse_bbc_forecast`. Validation and type safety; swap provider by writing a new parser.
3. **formatter.py** — One record → one sentence. Template with visible conditioning: `{conditions_phrase(precipitation_percent, wind_speed_kph)}`. Supports known BBC weather types; unknown values fall back to `.lower()` with a warning so LLMs can still reason on them.
4. **batch_generator.py** — Slice by calendar-day windows using a 06:00 cutoff: before/on 06:00 gives minimal window, after 06:00 gives +1 day. Produces Markdown with `## Date (day)` section headers.
5. **output_writer.py** — Atomic persistence via temp file + rename; ensures readers never see partial files.
6. **main.py** — CLI, threading (one thread per location), env var config (`WEATHER_BATCH_LOCATION`, `WEATHER_BATCH_OUTPUT`), exit codes (`10+N` for N failed locations; 126/127 for uv/uvx issues).

## Consequences

### Positive
- Clear separation of concerns; each module has a single responsibility
- Testable in isolation; comprehensive unit tests for data model and formatter
- Provider swapability: new weather API = new parser + same downstream model
- Operational resilience and observability (logging, exit codes, atomic writes)
- LLM-optimized output: natural sentences + Markdown section headers

### Negative
- Increased file count (6 modules vs. 1 script)
- Regex-based template parsing (`{func_name(var)}`) adds complexity but keeps transformations visible
- Thread-per-location doesn’t scale to hundreds of locations (acceptable for expected use case)

## Alternatives Considered and Rejected
- **Asyncio + httpx**: rejected; user requested classic threading for simplicity
- **Single output file**: rejected; atomic per-location requirement needs isolation anyway
- **Plain text output**: rejected; Markdown headers add semantic structure for LLMs without rigid machine formats

## Related Decisions
- Template syntax `{func_name(variable)}` makes data conditioning visible in the template string
- 06:00 cutoff aligns with "everyday data needs" — before 06:00 truncates, after gives full day
- Exit code 10+N lets shell scripts easily determine failure count without parsing logs
- Discovered weather types (`Thick Cloud`, `Sunny`) were added to the mapping dictionary

## References
- `data_model.py`: unified record schema + parser
- `formatter.py`: natural language templates + helpers
- `batch_generator.py`: temporal slicing + Markdown
- `main.py`: CLI + threading orchestration
- `api_client.py`: retry + rate-limit handling
