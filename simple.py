import requests
import json
from datetime import datetime, timedelta

def format_duration(seconds):
    """Convert duration in seconds to a readable format"""
    if seconds < 0:  # Running timer has negative duration
        return "In progress"
    
    # Create a timedelta and format it
    duration = timedelta(seconds=seconds)
    hours, remainder = divmod(duration.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    return f"{hours}h {minutes}m {seconds}s"

# API credentials
api_token = "cf35eb86aa00bfe5321d778fcf40d5a8"

# API endpoint for time entries
base_url = "https://api.track.toggl.com/api/v9"
time_entries_endpoint = f"{base_url}/me/time_entries"

try:
    # Make the API request
    response = requests.get(
        time_entries_endpoint,
        auth=(api_token, "api_token"),  # Using basic auth with API token
        params={"limit": 10}
    )
    
    # Check if the request was successful
    if response.status_code == 200:
        # Parse the JSON response
        time_entries = response.json()
        
        if not time_entries:
            print("No time entries found.")
        else:
            # Print the time entries
            print("Your last 10 Toggl time entries:")
            print("-" * 50)
            
            for entry in time_entries:
                # Convert timestamps to readable format
                start_time = "Unknown"
                if "start" in entry and entry["start"]:
                    try:
                        start_time = datetime.fromisoformat(entry["start"].replace("Z", "+00:00"))
                    except ValueError:
                        # Fall back to basic ISO format parsing
                        try:
                            start_time = datetime.strptime(entry["start"], "%Y-%m-%dT%H:%M:%S%z")
                        except ValueError:
                            pass  # Keep it as "Unknown"
                
                # Handle entries that are still running (no stop time)
                stop_time = "Not stopped"
                if "stop" in entry and entry["stop"]:
                    try:
                        stop_time = datetime.fromisoformat(entry["stop"].replace("Z", "+00:00"))
                    except ValueError:
                        try:
                            stop_time = datetime.strptime(entry["stop"], "%Y-%m-%dT%H:%M:%S%z")
                        except ValueError:
                            pass  # Keep it as "Not stopped"
                
                # Format duration
                duration = "Unknown"
                if "duration" in entry:
                    duration = format_duration(entry["duration"])
                
                # Print details
                print(f"Description: {entry.get('description', 'No description')}")
                print(f"Project ID: {entry.get('project_id', 'No project')}")
                print(f"Start: {start_time}")
                print(f"Stop: {stop_time}")
                print(f"Duration: {duration}")
                print("-" * 50)
    else:
        print(f"Error accessing Toggl API: {response.status_code}")
        print(response.text)

except requests.exceptions.RequestException as e:
    print(f"Request failed: {e}")
except json.JSONDecodeError:
    print("Failed to parse the API response as JSON")
except Exception as e:
    print(f"An error occurred: {e}")