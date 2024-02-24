import requests
from datetime import date, timedelta

today = date.today()

def get_interested_forecast_daterange():
    dates = [ today, today + timedelta(days=1), today + timedelta(days=2) ]

    return [date_item.strftime("%Y-%m-%d") for date_item in dates]

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
    print(f"forecasts for: { forecasts.keys() }")
    print(json.dumps(forecasts, indent=1))

def extract_and_flatten_forecast_objects(json):
    extracted_data = {}
    
    for forecast in json['forecasts']:
        for report in forecast['detailed']["reports"]:
            # Only process if it's a date we're interested in
            forecast_date = report['localDate']
            if forecast_date not in get_interested_forecast_daterange():
                break
            else:
                print(f"DEBUG: forecast for date {forecast_date} falls within interested daterange, processing")

            # Identify a weather forecast by concatenating the local date and time slot
            key = f"{forecast_date}T{report['timeslot']}"
            print(f"processing slot {key}")

            # Add the current report to the extracted data dictionary with the new key
            extracted_data[key] = report
            
    return extracted_data
        

LEVEN_ID = 2644577
location_id = LEVEN_ID  # This is the number you mentioned as a parameter
weather_data = grab_weather_data(location_id)

print(f"launching weather data refresh on date {today}")
print(get_interested_forecast_daterange())

if weather_data:
    parse_weather_data(weather_data)
