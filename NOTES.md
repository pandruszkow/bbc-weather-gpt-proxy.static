# Operational Notes

This document contains operational guidance, gotchas, and contextual information that doesn't fit the ADR format.

## Finding BBC Location IDs

The BBC Weather API uses numeric location IDs. To find one:

1. Visit https://www.bbc.co.uk/weather and search for a location
2. The URL will show the ID: `https://www.bbc.co.uk/weather/2644577`
3. The ID is `2644577`

Common UK locations:
- London: `2643743`
- Edinburgh: `2650225`
- Manchester: `2643123`
- Leven (Scotland): `2644577`

## API Behavior Observations

### Rate Limiting
- **Observed**: 429 responses include `Retry-After` header
- **Typical value**: 1-5 seconds
- **No hard limit documented**: The API is unofficial; behave responsibly

### Data Freshness
- Forecasts update approximately hourly
- `lastUpdated` timestamp in API response indicates freshness
- Historical data: The API drops past hours from `detailed.reports` as they elapse

### Coverage
- **Typical**: 13-14 days of hourly forecasts available
- **Minimum observed**: 5 days
- **Gap handling**: If a gap is detected (missing hour), the parser skips it; downstream logic may see non-contiguous timeslots

## Performance Characteristics

### Typical Runtime
- Single location, good connectivity: 2-5 seconds
- Three locations in parallel: 3-6 seconds (dominated by slowest fetch)
- With retries (transient failures): 10-30 seconds
- Hard timeout: 5 minutes per location

### Memory Usage
- Peak: ~2x the size of raw API response (parsing overhead)
- Typical: 5-20 MB depending on forecast depth
- Output files: ~50KB per day of coverage (text)

### Disk I/O
- Atomic writes use temp files in the target directory
- Ensure sufficient space in `WEATHER_BATCH_OUTPUT` for 3x expected output (temp + final + rename window)

## Error Recovery

### Scenario: Single Location Fails
**Symptom**: Exit code 11 (10+1), stderr shows location ID and error dump
**Recovery**: Retry just that location:
```bash
WEATHER_BATCH_LOCATION="failed_id" make run
```

### Scenario: All Locations Fail (Exit 1)
**Likely causes**:
- Network outage
- BBC API down or changed
- `uv`/`uvx` not available (exit 126/127)
**Recovery**: Check connectivity, verify API still responding:
```bash
curl "https://weather-broker-cdn.api.bbci.co.uk/en/forecast/aggregated/2644577"
```

### Scenario: Partial Output (Directory Non-Empty But Incomplete)
**Cause**: Process killed mid-write (SIGTERM, OOM killer)
**Recovery**: Delete output directory and re-run:
```bash
rm -rf output/"BBC Weather location 2644577"
WEATHER_BATCH_LOCATION="2644577" make run
```

### Scenario: Disk Full
**Symptom**: IOError during write, partial temp files
**Recovery**: Not handled gracefully (per requirements). Free disk space, delete output, re-run.

## Monitoring and Alerting

### Log Patterns to Watch

**INFO**: Normal operation
```
[2644577] Fetched 14 forecast blocks
[2644577] Generated output/BBC Weather location 2644577/Weather forecast for 2026-04-26 (next 24h).md (22 records)
```

**WARNING**: Recoverable, but notable
```
formatter - WARNING - Unmapped weather_type_text: 'Heavy Snow'. Using lowercase fallback.
```
Action: Add mapping to `WEATHER_TYPE_MAPPINGS` if this becomes common.

**ERROR**: Requires intervention
```
[2644577] Failed: APIRetryExhaustedError(...)
```
Action: Check stderr for full response dump. May indicate API change or block.

### Metrics to Track
- Success rate per location (exit codes)
- Frequency of "Unmapped weather_type_text" warnings (dictionary completeness)
- 429 rate limit hits (backpressure indicator)
- End-to-end latency (p95, p99)

## Testing with Mock Data

### Using the Fixture
```python
import json
from data_model import parse_bbc_forecast

with open('test_data/levenside_weather.json') as f:
    raw = json.load(f)
    
records = parse_bbc_forecast(raw, 2644577)
```

### Creating Test Scenarios
To test specific conditions (e.g., calm weather, high precipitation), edit the fixture:
```python
# Modify a record for testing
record["precipitationProbabilityInPercent"] = 0
record["windSpeedKph"] = 0
```

## Cron/Scheduling Recommendations

### Frequency
- **Minimum**: Every 6 hours (captures BBC updates)
- **Recommended**: Every 2 hours (balances freshness with rate limiting)
- **Maximum**: Hourly (diminishing returns, higher 429 risk)

### Timing
- Avoid exact hour boundaries (00:00, 06:00) — these are high-traffic
- Offset by random minutes: `17 * * * *` instead of `0 * * * *`

### Example Crontab
```cron
# Every 2 hours with 17-minute offset
17 */2 * * * cd /path/to/repo && WEATHER_BATCH_LOCATION="2644577" make run
```

## Security Considerations

### No Authentication Required
The BBC Weather API is public and unauthenticated. No API keys to rotate.

### User-Agent
The `requests` library default User-Agent is used. If BBC starts blocking, we may need to add a custom UA string identifying this tool.

### Output File Permissions
Files are created with default umask. If output directory is on shared storage, consider:
```bash
chmod 750 output/
```

## Known Limitations

1. **Single timezone**: All times are in the location's local timezone. No conversion to UTC or user's timezone.

2. **Hourly granularity only**: Half-hour forecasts (if BBC ever adds them) will be skipped by the parser.

3. **No severe weather alerts**: The API provides forecast data but not weather warnings/advisories.

4. **No historical queries**: Can only fetch current forecast data, not past weather.

5. **Location name drift**: BBC may rename locations. The `location_name` field is informational only; the ID is the stable identifier.

6. **Thread limits**: One thread per location. Running 100+ locations simultaneously may hit system thread limits or BBC rate limiting.

## Future Enhancements (Not Implemented)

### Short Term
- Wind direction inclusion (was scoped out but noted as useful)
- Humidity/pressure for health-related queries
- Configurable precipitation thresholds (currently hardcoded logic)

### Medium Term
- Caching layer to avoid refetching unchanged data
- Webhook/post-processing hook support
- Output format plugins (Markdown, plain text, etc.)

### Long Term
- Multi-provider support (fallback if BBC unavailable)
- Geocoding (city name → location ID lookup)
- Aggregation queries ("average temp across all monitored locations")

## Troubleshooting Checklist

| Problem | Check |
|---------|-------|
| Exit 127/126 | `which uv` and `which uvx` — is uv installed? |
| Exit 10+N | Check stderr for which location(s) failed and why |
| Empty output dir | Was there a disk full condition? Check `df -h` |
| Missing dates in output | Did BBC return full coverage? Check raw response |
| Formatting looks wrong | Check for "Unmapped weather_type_text" warnings |
| Slow execution | Are we hitting 429s? Check for rate limit warnings |
| High memory usage | How large is the API response? Typical is <1MB |

## Support and Maintenance

### When to Update Weather Type Mappings
After running for a few weeks, review logs for unmapped weather types:
```bash
grep "Unmapped weather_type_text" output.log | sort | uniq -c | sort -rn
```

Add high-frequency mappings to `formatter.py`.

### When to Update Dependencies
- `requests`: When security advisories published
- `pydantic`: When type validation bugs encountered or new features needed

### When to Revise This Document
- BBC API behavior changes significantly
- New operational patterns discovered
- Additional failure modes encountered
