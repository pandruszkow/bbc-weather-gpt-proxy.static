"""Unified data model for weather forecast records.

This module defines a provider-agnostic representation of weather data,
decoupling downstream logic from BBC-specific API structure.
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class WeatherRecord(BaseModel):
    """A unified, provider-agnostic weather forecast record.
    
    This model represents a single forecast instant (one hour slot)
    with standardized field names regardless of the source API.
    """
    
    # Temporal fields
    local_date: date = Field(description="Forecast date in local timezone (YYYY-MM-DD)")
    timeslot: str = Field(description="Time of day in HH:MM format")
    
    # Location metadata (carried through for context)
    location_id: int = Field(description="Source location identifier")
    location_name: Optional[str] = Field(default=None, description="Human-readable location name")
    
    # Temperature
    temperature_c: int = Field(description="Actual temperature in Celsius")
    feels_like_c: int = Field(description="Feels-like temperature in Celsius")
    
    # Conditions
    weather_type_text: str = Field(description="Weather condition summary (e.g., 'Partly Cloudy')")
    enhanced_description: Optional[str] = Field(default=None, description="Full natural language description")
    
    # Precipitation
    precipitation_percent: int = Field(description="Probability of precipitation (0-100)")
    precipitation_text: Optional[str] = Field(default=None, description="Human-readable precipitation summary")
    
    # Wind
    wind_speed_kph: int = Field(description="Sustained wind speed in km/h")
    wind_gust_kph: Optional[int] = Field(default=None, description="Gust speed in km/h")
    wind_direction: Optional[str] = Field(default=None, description="Wind direction abbreviation (e.g., 'SW')")
    wind_direction_full: Optional[str] = Field(default=None, description="Full wind direction description")
    wind_description: Optional[str] = Field(default=None, description="Full wind description text")
    
    # Additional metrics
    humidity: Optional[int] = Field(default=None, description="Relative humidity percentage")
    pressure: Optional[int] = Field(default=None, description="Barometric pressure in hPa")
    visibility: Optional[str] = Field(default=None, description="Visibility description")
    
    @field_validator('timeslot')
    @classmethod
    def validate_timeslot_format(cls, v: str) -> str:
        """Ensure timeslot is in HH:MM format."""
        try:
            datetime.strptime(v, '%H:%M')
        except ValueError:
            raise ValueError(f"timeslot must be in HH:MM format, got: {v}")
        return v
    
    @property
    def is_calm(self) -> bool:
        """True if no precipitation and no wind."""
        return self.precipitation_percent == 0 and self.wind_speed_kph == 0
    
    def __repr__(self) -> str:
        return f"WeatherRecord({self.local_date} {self.timeslot}: {self.temperature_c}°C, {self.weather_type_text})"


def parse_bbc_forecast(raw_data: dict, location_id: int) -> list[WeatherRecord]:
    """Parse BBC Weather API response into unified WeatherRecord objects.
    
    Args:
        raw_data: The JSON response from BBC Weather API
        location_id: The location ID used for the request
        
    Returns:
        A list of WeatherRecord objects, one per forecast timeslot
        
    Raises:
        KeyError: If expected keys are missing from the response
        ValueError: If data cannot be parsed into the expected format
    """
    records = []
    
    # Extract location metadata
    location_name = None
    if 'location' in raw_data and isinstance(raw_data['location'], dict):
        location_name = raw_data['location'].get('name')
    
    # BBC structure: forecasts[] -> detailed.reports[]
    if 'forecasts' not in raw_data:
        raise KeyError("Missing 'forecasts' key in API response")
    
    for forecast in raw_data['forecasts']:
        if 'detailed' not in forecast or 'reports' not in forecast['detailed']:
            continue
            
        for report in forecast['detailed']['reports']:
            try:
                record = WeatherRecord(
                    local_date=date.fromisoformat(report['localDate']),
                    timeslot=report['timeslot'],
                    location_id=location_id,
                    location_name=location_name,
                    temperature_c=report['temperatureC'],
                    feels_like_c=report['feelsLikeTemperatureC'],
                    weather_type_text=report['weatherTypeText'],
                    enhanced_description=report.get('enhancedWeatherDescription'),
                    precipitation_percent=report['precipitationProbabilityInPercent'],
                    precipitation_text=report.get('precipitationProbabilityText'),
                    wind_speed_kph=report['windSpeedKph'],
                    wind_gust_kph=report.get('gustSpeedKph'),
                    wind_direction=report.get('windDirection'),
                    wind_direction_full=report.get('windDirectionFull'),
                    wind_description=report.get('windDescription'),
                    humidity=report.get('humidity'),
                    pressure=report.get('pressure'),
                    visibility=report.get('visibility'),
                )
                records.append(record)
            except (KeyError, ValueError) as e:
                # Skip malformed records but continue processing
                continue
    
    return records
