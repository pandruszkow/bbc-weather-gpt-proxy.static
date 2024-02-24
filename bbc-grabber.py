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

LEVEN_ID = 2644577
location_id = LEVEN_ID  # This is the number you mentioned as a parameter
weather_data = download_weather_data(location_id)

if weather_data:
    print(weather_data)  # This will print the nested dictionary
