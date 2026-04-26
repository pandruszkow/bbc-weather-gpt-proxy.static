# ADR 001: BBC Weather Batch Generator Architecture

## Status
Accepted

## Context

The BBC Weather scraper from 2024 needed modernization. The original script (`bbc-grabber.py`) was a monolithic script that mixed concerns: HTTP fetching, JSON parsing, data transformation, and output generation. As the BBC API evolves and requirements expand, this tight coupling became problematic.

### Key Requirements

1. **API resilience**: Handle transient failures, rate limiting (429), and network issues gracefully
2. **Data model decoupling**: Isolate downstream logic from BBC-specific API structure to allow provider swapping
3. **Natural language output**: Generate LLM-friendly text for weather-based decision making (attire, laundry drying, rain likelihood)
4. **Multiple temporal windows**: Support 24h, 3-day, and 1-week forecast batches
5. **Multi-location support**: Process multiple locations in parallel with per-location atomicity
6. **Operational clarity**: Clear exit codes, logging, and environment-based configuration

### Design Constraints

- Target audience: Large language models consuming the output as a data source
- Output must be naturalistic (human-readable) not machine-formatted (JSON)
- Must handle BBC API changes gracefully or fail loudly with full diagnostics
- Must support being run as part of automated pipelines with reliable error detection

---

## Decision

We will adopt a **modular pipeline architecture** with six distinct layers.

### 1. API Client (`api_client.py`)

**Responsibility**: Raw HTTP I/O only. No parsing, no transformation.

**Retry Strategy**:
- Exponential backoff with jitter: `base_delay * 2^attempt` with 0-25% random variance
- 5 retry attempts maximum
- 5-minute hard timeout per request (wall clock from first attempt)
- Special handling for HTTP 429 (rate limit): obeys `Retry-After` header when present, falls back to exponential backoff when absent
- Server errors (5xx) trigger retry; client errors (4xx except 429) do not

**Rationale**: The BBC API is unofficial and may have transient failures or rate limiting. Exponential backoff prevents thundering herd while jitter prevents synchronized retries across multiple instances. The hard timeout ensures hung requests don't block the pipeline indefinitely.

### 2. Data Model (`data_model.py`)

**Responsibility**: Parse provider-specific JSON into a unified, provider-agnostic representation.

**Key Components**:
- `WeatherRecord`: Pydantic model with validation for all forecast fields
- `parse_bbc_forecast()`: BBC-specific parser that extracts hourly records from the nested `forecasts[].detailed.reports[]` structure
- Field mapping normalizes BBC naming (`temperatureC` → `temperature_c`, `localDate` → `local_date`)

**Swapability**: A new weather provider requires only a new parser function that returns `List[WeatherRecord]`. Downstream code (formatter, batch generator) remains unchanged.

**Rationale**: Decoupling protects the investment in formatting and generation logic. If BBC changes their API or blocks access, we can swap to OpenWeatherMap, Met Office, etc. by changing only the client and parser.

### 3. Formatter (`formatter.py`)

**Responsibility**: Transform one `WeatherRecord` into one English sentence.

**Template Syntax**: `{function_name(variable)}` makes conditioning visible in the template:

```
Weather forecast for {local_date} at {conditioned_timeslot}: Temperature will be 
{temperature_c}°C (feels like {feels_like_c}°C). {conditions_phrase(precipitation_percent, wind_speed_kph)} 
Expect {condition_weather_type(weather_type_text)}.
```

**Conditioning Functions**:

1. **`conditioned_timeslot(timeslot)`**:
   - `12:00` → `"noon"` (clearer than "12:00h" which could be misread)
   - All others → `"{timeslot}h"` (e.g., "14:00h", "00:00h")

2. **`conditions_phrase(precipitation_percent, wind_speed_kph)`**:
   Handles four cases to avoid awkward phrasing:
   - `0%, 0` → `"No winds or precipitation expected."`
   - `0%, >0` → `"No precipitation expected, with winds at {speed} km/h."`
   - `>0%, 0` → `"A {pct}% chance of precipitation, with no wind expected."`
   - `>0%, >0` → `"A {pct}% chance of precipitation, with winds at {speed} km/h."`

   **Rationale**: Zero values are common. Saying "0% chance" and "0 km/h" repeatedly is noisy. The combined "no winds or precipitation" case handles the most common calm condition elegantly.

3. **`condition_weather_type(weather_type_text)`**:
   - Dictionary lookup for known BBC values (e.g., `"Clear Sky"` → `"clear skies"`)
   - Unknown values fall back to `.lower()` and log a warning for dictionary updates
   
   **Rationale**: BBC's `weatherTypeText` is title-cased ("Partly Cloudy"), which looks jarring mid-sentence. A lookup allows grammatical fixes ("Clear Sky" → "clear skies"). The warning + fallback strategy lets us discover new values from production logs without breaking output.

4. **`format_date_header(target_date, run_date)`**:
   - Same day as run: `"Today, 25th of April (Saturday)"`
   - Next day: `"Tomorrow, 26th of April (Sunday)"`
   - Future days: `"27th of April (Monday)"` (no prefix)

   **Rationale**: LLMs receiving "Will I be able to do laundry on Thursday?" can match against "Thursday" in the header more easily than against ISO dates. The relative prefixes (Today/Tomorrow) provide immediate temporal context.

**Why visible conditioning in templates?**: The `{func(var)}` syntax keeps the transformation logic modular (in functions) while making the data flow explicit in the template. An LLM reading the template can trace exactly which field goes through which transformation.

### 4. Batch Generator (`batch_generator.py`)

**Responsibility**: Slice records by temporal window, group by calendar day, generate Markdown.

**Window Sizing Logic**:

| Window | Before/On 06:00 | After 06:00 |
|--------|-----------------|-------------|
| 24h    | Today only      | Today + Tomorrow |
| 3d     | Today + 2 more full days | Today + 3 more full days |
| 1w     | Today + 6 more full days | Today + 7 more full days |

**Rationale for 06:00 cutoff**: Early morning runs (before 06:00) are likely cron jobs seeking "today's forecast." By 06:00, users are awake and planning — they benefit from seeing tomorrow's data too. The cutoff aligns with "everyday data need expectations" rather than being blindly machine-like.

**Atomic Per-Location Writes**: All batch files for a location succeed or fail together. On any failure (insufficient data, disk error), the location's output directory is left empty. This prevents partial/corrupt data from being consumed downstream.

**Markdown Structure**:
```markdown
## Today, 26th of April (Sunday)

[sentences for this date]

## Tomorrow, 27th of April (Monday)

[sentences for this date]
```

**Rationale for Markdown**: LLMs are natural language processors. Machine formats (JSON, CSV) require explicit parsing. Markdown with `##` headers provides semantic structure (date boundaries) while remaining natively parseable as text. The headers act as signposts for temporal queries.

### 5. Output Writer (`output_writer.py`)

**Responsibility**: Atomic file persistence.

**Implementation**: Write to temp file in target directory, then `os.rename()` to final name. This ensures readers never see partially written files.

**Rationale**: If the process crashes mid-write, a half-written file could be ingested by a downstream consumer. Atomic rename guarantees file content is complete and consistent once the filename appears.

### 6. Main / CLI (`main.py`)

**Responsibility**: Orchestration, CLI, threading, exit codes.

**Parallelism Model**: One thread per location. Classic `threading.Thread`, no `asyncio`, no `concurrent.futures`.

**Rationale**: The user explicitly requested "classic" threading for simplicity. The use case (dozens of locations, not thousands) doesn't justify async complexity. Threads are I/O-bound (waiting on HTTP), so GIL contention is minimal.

**Per-Location Processing**:
1. Fetch raw data (with retries)
2. Parse into unified records
3. Generate all batch files via staging directory
4. Atomic rename of staging directory to final location

**Configuration**:
- `WEATHER_BATCH_LOCATION`: Location IDs, separated by comma/semicolon/space
- `WEATHER_BATCH_OUTPUT`: Override output directory (env var takes precedence over CLI)

**Exit Codes**:
- `0`: All locations succeeded
- `1`: Generic error
- `10+N`: N locations failed (capped at 100)
- `126`: `uv`/`uvx` not executable
- `127`: `uv`/`uvx` not found

**Rationale for 10+N**: Shell scripts can easily check `if [ $? -gt 9 ]; then` to detect partial failures without parsing log output. The cap at 100 keeps codes within a reasonable range.

**Failure Handling**:
- Per-request retry with exponential backoff (see API Client)
- Per-location atomicity (see Batch Generator)
- Failed locations are logged to stderr with full response dump of final failed request
- Processing continues for other locations; exit code reflects aggregate failure count

---

## Consequences

### Positive

- **Clear separation of concerns**: Each module has a single, well-defined responsibility
- **Testability**: Each layer can be unit tested in isolation with mocked dependencies
- **Provider swapability**: New weather API requires only new client + parser
- **Operational resilience**: Retry logic, atomic writes, clear failure modes, domain-specific exit codes
- **LLM-optimized output**: Natural language sentences, Markdown structure, relative date headers
- **Data provenance visibility**: Template syntax shows exactly which fields are conditioned and how

### Negative

- **Increased file count**: 6 Python modules vs. 1 original script
- **Template parsing complexity**: The `{func(var)}` syntax requires regex-based parsing
- **Thread overhead**: One thread per location doesn't scale to thousands (acceptable for expected use case)
- **Weather type dictionary maintenance**: New `weatherTypeText` values from BBC require dictionary updates

---

## Alternatives Considered

### Asyncio with httpx

**Status**: Rejected

**Reason**: User explicitly requested "classic" threading. Asyncio adds cognitive overhead (event loops, async/await viral infection). The workload is I/O-bound with moderate concurrency (tens of locations, not thousands), so threading is sufficient and simpler to reason about.

### Single Output File Per Run

**Status**: Rejected

**Reason**: Atomic per-location requirement necessitates separate directories. Multiple files also let downstream consumers subscribe to specific temporal windows (e.g., only 24h forecasts) without parsing a larger file.

### Pure Text Output (No Markdown)

**Status**: Rejected

**Reason**: Markdown `##` headers provide valuable semantic structure for date boundaries without requiring rigid machine formats (JSON). LLMs can use the headers as anchors for temporal queries.

### JSON Output for Machine Parsing

**Status**: Rejected

**Reason**: The target audience is LLMs, which are natively natural language processors. JSON requires explicit parsing; natural language is their native input. The slight loss of precision is offset by the elimination of a parsing step.

### Including Wind Direction

**Status**: Rejected (noted for future enhancement)

**Reason**: User scoped this out for the initial implementation. Wind speed alone is sufficient for the use cases (attire, drying clothes, rain likelihood). Direction may be added in a future endpoint for other use cases (cycling, sailing).

### Including Humidity and Pressure

**Status**: Rejected

**Reason**: While present in the API, they were deemed non-essential for the core use cases. Can be added later if needed for specific health-related queries (migraines, respiratory).

---

## Related Decisions

### Why `noon` instead of `12:00h`

`12:00` is ambiguous — noon or midnight? In 24-hour format it's noon, but users might misread. `noon` is unambiguous. All other times get the `h` suffix to reinforce 24-hour format.

### Why `0%` → "no precipitation expected" but `>0%` → raw value

Zero precipitation is extremely common. Replacing it with a phrase eliminates repetitive noise. For non-zero values, raw percentages let the LLM judge "slight" vs "moderate" risk itself and detect trends/peaks across the day.

### Why Calendar-Day Windows Instead of Rolling Hours

Calendar days align with human planning. "What will the weather be tomorrow?" is a calendar question, not a 24-hour-from-now question. The 06:00 cutoff provides a grace period for early-morning data freshness without truncating useful data.

### Why Exit Codes Instead of Structured Logs

Shell scripts and pipeline orchestrators can check exit codes easily (`if [ $? -eq 0 ]`). Parsing log output for success/failure is fragile. Domain-specific codes (`10+N`) allow automated retry decisions (e.g., retry if `? -gt 9`, fail fast if `? -eq 1`).

---

## References

- `data_model.py`: Unified `WeatherRecord` schema and BBC parser
- `formatter.py`: Template engine and conditioning functions
- `batch_generator.py`: Temporal window slicing and Markdown generation
- `main.py`: CLI entrypoint and threading orchestration
- `adr/`: This directory contains architecture decision records
