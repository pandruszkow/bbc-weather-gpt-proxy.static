"""BBC Weather API client with retry logic and rate limit handling.

This module handles all HTTP I/O with the BBC Weather API endpoint,
including exponential backoff retries and 429 (rate limit) response handling.
"""

import logging
import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

import requests

# BBC Weather API endpoint template
BBC_WEATHER_API_URL = "https://weather-broker-cdn.api.bbci.co.uk/en/forecast/aggregated/{location_id}"

# Retry configuration
MAX_RETRIES = 5
HARD_TIMEOUT_SECONDS = 300  # 5 minutes per request
BASE_DELAY_SECONDS = 1
MAX_DELAY_SECONDS = 30
MAX_RETRY_AFTER_SECONDS = 120  # don't let a hostile/buggy Retry-After park a thread for hours

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Base exception for API client errors."""
    pass


class APIRetryExhaustedError(APIError):
    """Raised when all retries are exhausted."""
    pass


class APITimeoutError(APIError):
    """Raised when the hard timeout is exceeded."""
    pass


def fetch_weather_data(
    location_id: int,
    max_retries: int = MAX_RETRIES,
    hard_timeout: float = HARD_TIMEOUT_SECONDS,
) -> dict:
    """Fetch weather data from BBC API with retry logic.
    
    Implements exponential backoff with jitter for transient failures.
    Special handling for 429 (rate limit) responses: obeys Retry-After header.
    
    Args:
        location_id: BBC location identifier
        max_retries: Maximum number of retry attempts
        hard_timeout: Maximum total time to spend on this request
        
    Returns:
        Parsed JSON response as dictionary
        
    Raises:
        APIRetryExhaustedError: If all retries fail
        APITimeoutError: If hard timeout is exceeded
        APIError: For other HTTP errors
    """
    url = BBC_WEATHER_API_URL.format(location_id=location_id)
    start_time = time.time()
    last_response: Optional[requests.Response] = None
    
    def wait(delay: float, attempt: int) -> None:
        """Sleep before the next attempt, never past the hard timeout."""
        if attempt + 1 >= max_retries:
            return  # no attempt follows; sleeping would only delay the error
        remaining = hard_timeout - (time.time() - start_time)
        if delay >= remaining:
            raise APITimeoutError(
                f"Hard timeout of {hard_timeout}s would be exceeded by a {delay:.1f}s wait "
                f"after {attempt + 1} attempts"
            )
        time.sleep(delay)
    
    for attempt in range(max_retries):
        # Check hard timeout
        elapsed = time.time() - start_time
        if elapsed >= hard_timeout:
            raise APITimeoutError(
                f"Hard timeout of {hard_timeout}s exceeded after {attempt} attempts"
            )
        
        try:
            remaining_timeout = hard_timeout - elapsed
            logger.debug(f"Fetching {url} (attempt {attempt + 1}/{max_retries}, timeout={remaining_timeout:.1f}s)")
            
            response = requests.get(url, timeout=min(30, remaining_timeout))
        except requests.RequestException as e:
            # Covers timeouts and connection errors
            delay = calculate_backoff_delay(attempt)
            logger.warning(f"Request error: {e!r}, retrying in {delay:.1f}s")
            wait(delay, attempt)
            continue
        
        last_response = response
        
        # Success case
        if response.status_code == 200:
            return response.json()
        
        # Rate limit case - obey Retry-After if present, capped
        if response.status_code == 429:
            delay = parse_retry_after(response.headers.get('Retry-After'))
            if delay is None:
                delay = calculate_backoff_delay(attempt)
                logger.warning(f"Rate limited (429), no usable Retry-After, using backoff: {delay:.1f}s")
            else:
                delay = min(delay, MAX_RETRY_AFTER_SECONDS)
                logger.warning(f"Rate limited (429), obeying Retry-After (capped at {MAX_RETRY_AFTER_SECONDS}s): {delay:.1f}s")
            wait(delay, attempt)
            continue
        
        # Client errors (4xx except 429) - don't retry. Raised as APIError,
        # not requests.HTTPError: the latter is a RequestException and used to
        # be caught by the retry handler, so a 404 was retried five times.
        if 400 <= response.status_code < 500:
            raise APIError(
                f"HTTP {response.status_code} for {url}; not retrying. "
                f"Body (first 500 chars): {response.text[:500]}"
            )
        
        # Server errors (5xx) and anything unexpected - retry with backoff
        delay = calculate_backoff_delay(attempt)
        logger.warning(f"HTTP {response.status_code}, retrying in {delay:.1f}s")
        wait(delay, attempt)
    
    # All retries exhausted
    error_msg = f"Failed to fetch weather data after {max_retries} attempts"
    if last_response is not None:
        error_msg += f"\nLast response status: {last_response.status_code}"
        error_msg += f"\nLast response headers: {dict(last_response.headers)}"
        error_msg += f"\nLast response body (first 500 chars): {last_response.text[:500]}"
    
    raise APIRetryExhaustedError(error_msg)


def parse_retry_after(value: Optional[str]) -> Optional[float]:
    """Parse a Retry-After header (delta-seconds or HTTP-date) into seconds.
    
    Returns None if absent or unparseable; never negative.
    """
    if not value:
        return None
    value = value.strip()
    try:
        return max(0.0, float(int(value)))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


def calculate_backoff_delay(attempt: int) -> float:
    """Calculate exponential backoff delay with jitter.
    
    Uses exponential backoff: base_delay * 2^attempt
    Adds random jitter (0-25% of calculated delay)
    Caps at max_delay_seconds
    
    Args:
        attempt: The current attempt number (0-indexed)
        
    Returns:
        Delay in seconds to wait before next retry
    """
    delay = BASE_DELAY_SECONDS * (2 ** attempt)
    delay = min(delay, MAX_DELAY_SECONDS)
    
    # Add jitter: 0-25% random variance
    jitter = delay * 0.25 * random.random()
    delay += jitter
    
    return delay
