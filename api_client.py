"""BBC Weather API client with retry logic and rate limit handling.

This module handles all HTTP I/O with the BBC Weather API endpoint,
including exponential backoff retries and 429 (rate limit) response handling.
"""

import json
import logging
import random
import time
from typing import Optional

import requests

# BBC Weather API endpoint template
BBC_WEATHER_API_URL = "https://weather-broker-cdn.api.bbci.co.uk/en/forecast/aggregated/{location_id}"

# Retry configuration
MAX_RETRIES = 5
HARD_TIMEOUT_SECONDS = 300  # 5 minutes per request
BASE_DELAY_SECONDS = 1
MAX_DELAY_SECONDS = 30

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
            last_response = response
            
            # Success case
            if response.status_code == 200:
                return response.json()
            
            # Rate limit case - obey Retry-After if present
            if response.status_code == 429:
                retry_after = response.headers.get('Retry-After')
                if retry_after:
                    try:
                        delay = int(retry_after)
                        logger.warning(f"Rate limited (429), obeying Retry-After: {delay}s")
                    except ValueError:
                        delay = calculate_backoff_delay(attempt)
                        logger.warning(f"Rate limited (429), invalid Retry-After, using backoff: {delay:.1f}s")
                else:
                    delay = calculate_backoff_delay(attempt)
                    logger.warning(f"Rate limited (429), no Retry-After header, using backoff: {delay:.1f}s")
                
                time.sleep(delay)
                continue
            
            # Server errors (5xx) - retry with backoff
            if 500 <= response.status_code < 600:
                delay = calculate_backoff_delay(attempt)
                logger.warning(f"Server error {response.status_code}, retrying in {delay:.1f}s")
                time.sleep(delay)
                continue
            
            # Client errors (4xx except 429) - don't retry
            if 400 <= response.status_code < 500:
                response.raise_for_status()
            
            # Other status codes - retry
            delay = calculate_backoff_delay(attempt)
            logger.warning(f"Unexpected status {response.status_code}, retrying in {delay:.1f}s")
            time.sleep(delay)
            
        except requests.Timeout:
            delay = calculate_backoff_delay(attempt)
            logger.warning(f"Request timeout, retrying in {delay:.1f}s")
            time.sleep(delay)
            
        except requests.RequestException as e:
            delay = calculate_backoff_delay(attempt)
            logger.warning(f"Request error: {e}, retrying in {delay:.1f}s")
            time.sleep(delay)
    
    # All retries exhausted
    error_msg = f"Failed to fetch weather data after {max_retries} attempts"
    if last_response is not None:
        error_msg += f"\nLast response status: {last_response.status_code}"
        error_msg += f"\nLast response headers: {dict(last_response.headers)}"
        error_msg += f"\nLast response body (first 500 chars): {last_response.text[:500]}"
    
    raise APIRetryExhaustedError(error_msg)


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
