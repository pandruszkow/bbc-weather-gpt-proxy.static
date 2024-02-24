import requests

def grab_weather_data(location_id):
    # Construct the URL with the given location ID
    url = f"https://weather-broker-cdn.api.bbci.co.uk/en/forecast/aggregated/{location_id}"

    try:
        # Grab weather for location ID
        response = requests.get(url)
        # Crash if error
        response.raise_for_status()
        
        # Parse the JSON response into a nested dictionary
        weather_data = response.json()
        return weather_data

    except requests.RequestException as e:
        print(f"Error while fetching weather data: {e}")
        return None

def parse_weather_data(json):
    hr_location = json["location"]["name"]
    print(f"Human readable location: { hr_location }")
    print("next 48 hours")
    forecasts = extract_and_flatten_forecast_objects(json)
    forecasts = forecasts
    print(f"forecasts for: { forecasts.keys() }")

def extract_and_flatten_forecast_objects(json):
    extracted_data = {}
    for forecast in json['forecasts']:
        processing_limit = 6 + 24 + 24 # We want to only grab data up to 05:59 today + the next 48 hours. No sense grabbing more than that.
        for report in forecast['detailed']["reports"][0:2]:
            # Create a new key for the current report by concatenating the local date and time slot
            key = f"{report['localDate']}T{report['timeslot']}"
            print(f"processing slot {key}")

            # Add the current report to the extracted data dictionary with the new key
            extracted_data[key] = report
            
            # if we're beyond the point of stopping processing, stop the parsing loop
            --processing_limit
            print(f"remaining {processing_limit} entries before cutoff")
            if processing_limit <= 0:
                break
            
    return extracted_data
        

LEVEN_ID = 2644577
location_id = LEVEN_ID  # This is the number you mentioned as a parameter
weather_data = grab_weather_data(location_id)

if weather_data:
    parse_weather_data(weather_data)
