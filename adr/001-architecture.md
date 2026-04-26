# ADR 001: BBC Weather Batch Generator Architecture

## Status
Accepted

## Context
The BBC Weather scraper from 2024 needed modernization. The original script (`bbc-grabber.py`) was a monolithic script that mixed concerns: HTTP fetching, JSON parsing, data transformation, and output generation. As the BBC API evolves and requirements expand, this tight coupling became problematic.

Key requirements for the new architecture:
1. **API resilience**: Handle transient failures, rate limiting (429), and network issues gracefully
2. **Data model decoupling**: Isolate downstream logic from BBC-specific API structure
3. **Natural language output**: Generate LLM-friendly text for weather-based decision making (attire, laundry drying, rain likelihood)
4. **Multiple temporal windows**: Support 24h, 3-day, and 1-week forecast batches
5. **Multi-location support**: Process multiple locations in parallel
6. **Atomic operations**: All files for a location succeed or fail together
7. **Operational clarity**: Clear exit codes, logging, and environment-based configuration

## Decision

We will adopt a **modular pipeline architecture** with six distinct layers:

### 1. API Client (`api_client.py`)
- **Responsibility**: HTTP I/O only
- **Key features**: 
  - Exponential backoff with jitter
  - Special 429 handling (obeys `Retry-After` header)
  - 5 retries, 5-minute hard timeout per request
  - Detailed error logging with response dumps on final failure

### 2. Data Model (`data_model.py`)
- **Responsibility**: Provider-agnostic data representation
- **Key features**:
  - Pydantic-based `WeatherRecord` class
  - BBC-specific parser (`parse_bbc_forecast`)
  - Validation and type safety
  - **Swapability**: New provider = new parser function, same output model

### 3. Formatter (`formatter.py`)
- **Responsibility**: One record → one sentence
- **Key features**:
  - Template-based with function call syntax: `{conditions_phrase(precipitation_percent, wind_speed_kph)}`
  - Four-condition phrase logic for wind/precipitation combinations
  - Weather type text conditioning with fallback logging
  - Human-readable date headers with relative prefixes (Today/Tomorrow)

### 4. Batch Generator (`batch_generator.py`)
- **Responsibility**: Temporal window slicing and Markdown generation
- **Key features**:
  - 06:00 cutoff logic for window sizing
  - Calendar-day grouping with `##` section headers
  - Complete coverage validation (atomic per-location)

### 5. Output Writer (`output_writer.py`)
- **Responsibility**: Atomic file persistence
- **Key features**:
  - Temp file + rename pattern for atomic writes
  - Directory creation as needed

### 6. Main / CLI (`main.py`)
- **Responsibility**: Orchestration and CLI
- **Key features**:
  - Thread-per-location parallelism (classic threading, no futures/async)
  - Environment variable configuration (`WEATHER_BATCH_LOCATION`, `WEATHER_BATCH_OUTPUT`)
  - Domain-specific exit codes: `10+N` for N failed locations

## Consequences

### Positive
- **Clear separation of concerns**: Each module has a single, well-defined responsibility
- **Testability**: Each layer can be unit tested in isolation
- **Provider swapability**: New weather API = new `api_client.py` + `data_model.py` parser
- **Operational resilience**: Retry logic, atomic writes, and clear failure modes
- **LLM-optimized output**: Natural language sentences with structured Markdown sections

### Negative
- **Increased file count**: 6 Python modules vs. 1 original script
- **Template parsing complexity**: The `{func_name(var)}` syntax requires regex-based parsing
- **Thread overhead**: One thread per location may not scale to hundreds of locations (acceptable for expected use case)

## Alternatives Considered

### Alternative 1: Asyncio with httpx
**Rejected**: User explicitly requested "classic" threading. Asyncio adds cognitive overhead and the use case (few locations, I/O-bound) doesn't justify it.

### Alternative 2: Single output file per run
**Rejected**: Atomic per-location requirement means we need separate directories anyway. Multiple files also let users subscribe to specific temporal windows.

### Alternative 3: Pure text output (no Markdown)
**Rejected**: Markdown `##` headers provide valuable semantic structure for LLMs parsing the output without requiring rigid machine formats (JSON).

## Related Decisions

- **Template syntax**: `{func_name(variable)}` makes data conditioning visible in the template string while keeping transformation logic modular
- **06:00 cutoff**: Aligns with "everyday data needs" — users running before 06:00 get minimal data, after 06:00 get bonus day
- **Exit code 10+N**: Allows shell scripts to easily determine how many locations failed without parsing logs

## References

- `data_model.py`: Unified record schema
- `formatter.py`: Natural language templates
- `batch_generator.py`: Temporal window logic
- `main.py`: CLI and threading orchestration