"""Natural language formatter for weather records.

Transforms unified WeatherRecord objects into English sentences suitable
for LLM consumption. Includes template parsing and field conditioning.
"""

import logging
import re
from typing import Callable

from data_model import WeatherRecord

logger = logging.getLogger(__name__)

# Weather type text mappings: raw BBC value -> conditioned output
WEATHER_TYPE_MAPPINGS = {
    "Partly Cloudy": "partly cloudy",
    "Sunny Intervals": "sunny intervals",
    "Light Cloud": "light cloud",
    "Clear Sky": "clear skies",
    "Light Rain Showers": "light rain showers",
}

# Template for single record output
# Uses {function_name(variable)} syntax for conditioned fields
RECORD_TEMPLATE = (
    "Weather forecast for {local_date} at {conditioned_timeslot}: "
    "Temperature will be {temperature_c}°C (feels like {feels_like_c}°C). "
    "{conditions_phrase(precipitation_percent, wind_speed_kph)} "
    "Expect {condition_weather_type(weather_type_text)}."
)

# Regex to match {func_name(var1, var2)} or {var} patterns
TEMPLATE_PATTERN = re.compile(r'\{([a-zA-Z_][a-zA-Z0-9_]*(?:\([a-zA-Z_][a-zA-Z0-9_, ]*\))?)\}')


def format_record(record: WeatherRecord) -> str:
    """Format a WeatherRecord into a natural language sentence.
    
    Parses the template, resolves variable references and function calls,
    and returns the final formatted string.
    
    Args:
        record: A unified weather record
        
    Returns:
        A formatted sentence describing the forecast
    """
    def replacer(match: re.Match) -> str:
        expr = match.group(1)
        
        # Check if it's a function call like conditions_phrase(a, b)
        if '(' in expr and ')' in expr:
            func_name = expr[:expr.index('(')]
            args_str = expr[expr.index('(')+1:expr.index(')')]
            arg_names = [a.strip() for a in args_str.split(',')]
            
            # Get the function
            func = globals().get(func_name)
            if func is None:
                logger.error(f"Unknown function in template: {func_name}")
                return f"[{func_name}](ERROR)"
            
            # Get argument values from record
            arg_values = []
            for arg_name in arg_names:
                if hasattr(record, arg_name):
                    arg_values.append(getattr(record, arg_name))
                else:
                    logger.error(f"Unknown field in template: {arg_name}")
                    arg_values.append(None)
            
            return func(*arg_values)
        else:
            # It's a simple variable reference
            if hasattr(record, expr):
                value = getattr(record, expr)
                if expr == 'local_date':
                    return str(value)
                return str(value)
            else:
                # Check for conditioned field functions
                if expr == 'conditioned_timeslot':
                    return conditioned_timeslot(record.timeslot)
                elif expr == 'condition_weather_type':
                    return condition_weather_type(record.weather_type_text)
                else:
                    logger.error(f"Unknown field in template: {expr}")
                    return f"[{expr}]"
    
    return TEMPLATE_PATTERN.sub(replacer, RECORD_TEMPLATE)


def conditioned_timeslot(timeslot: str) -> str:
    """Condition a timeslot for natural language output.
    
    Converts '12:00' to 'noon', all others get 'h' suffix.
    
    Args:
        timeslot: Time in HH:MM format
        
    Returns:
        Conditioned timeslot string
    """
    if timeslot == "12:00":
        return "noon"
    return f"{timeslot}h"


def conditions_phrase(precipitation_percent: int, wind_speed_kph: int) -> str:
    """Generate the combined conditions phrase.
    
    Handles the four cases:
    - Both zero: "No winds or precipitation expected."
    - Only wind zero: "A X% chance of precipitation, with no wind expected."
    - Only precipitation zero: "No precipitation expected, with winds at Y km/h."
    - Neither zero: "A X% chance of precipitation, with winds at Y km/h."
    
    Args:
        precipitation_percent: Probability of precipitation (0-100)
        wind_speed_kph: Wind speed in km/h
        
    Returns:
        The appropriate conditions phrase
    """
    if precipitation_percent == 0 and wind_speed_kph == 0:
        return "No winds or precipitation expected."
    
    if precipitation_percent == 0:
        # No precipitation, some wind
        return f"No precipitation expected, with winds at {wind_speed_kph} km/h."
    
    if wind_speed_kph == 0:
        # Some precipitation, no wind
        return f"A {precipitation_percent}% chance of precipitation, with no wind expected."
    
    # Both non-zero
    return f"A {precipitation_percent}% chance of precipitation, with winds at {wind_speed_kph} km/h."


def condition_weather_type(weather_type_text: str) -> str:
    """Condition weather type text for natural language output.
    
    Uses a lookup dictionary for known BBC values, with fallback to
    lowercase for unknown values. Logs unmapped values for future
    dictionary updates.
    
    Args:
        weather_type_text: Raw weather type text from API
        
    Returns:
        Conditioned weather type string
    """
    if weather_type_text in WEATHER_TYPE_MAPPINGS:
        return WEATHER_TYPE_MAPPINGS[weather_type_text]
    
    # Unmapped value - log for future updates
    logger.warning(
        f"Unmapped weather_type_text: '{weather_type_text}'. "
        f"Using lowercase fallback. Consider adding to WEATHER_TYPE_MAPPINGS."
    )
    
    return weather_type_text.lower()


def format_date_header(target_date, run_date: date) -> str:
    """Format a date header with relative prefix.
    
    Generates headers like:
    - "Today, 25th of April (Friday)"
    - "Tomorrow, 26th of April (Saturday)"
    - "27th of April (Sunday)"
    
    Args:
        target_date: The date being formatted
        run_date: The date the script was run (for relative calculation)
        
    Returns:
        Formatted date header string
    """
    # Calculate day difference
    delta_days = (target_date - run_date).days
    
    # Determine prefix
    if delta_days == 0:
        prefix = "Today, "
    elif delta_days == 1:
        prefix = "Tomorrow, "
    else:
        prefix = ""
    
    # Format day of month with ordinal suffix
    day = target_date.day
    if 11 <= day <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    
    # Day of week
    day_name = target_date.strftime("%A")
    
    # Month name
    month_name = target_date.strftime("%B")
    
    return f"{prefix}{day}{suffix} of {month_name} ({day_name})"
