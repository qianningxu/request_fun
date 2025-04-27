import functions_framework
import requests
import json
from datetime import datetime, timedelta
import os

@functions_framework.http
def request_rn(request):
    """HTTP Cloud Function to retrieve Toggl time entries.
    Args:
        request (flask.Request): The request object.
    Returns:
        The response text, or any set of values that can be turned into a
        Response object using `make_response`.
    """
    # Enable CORS for browser-based requests
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)
    
    headers = {'Access-Control-Allow-Origin': '*'}
    
    # Get API token from environment variable
    api_token = os.environ.get('TOGGL_API_TOKEN')
    if not api_token:
        return (json.dumps({'error': 'API token not configured'}), 500, headers)
    
    def format_duration(seconds):
        """Convert duration in seconds to a readable format"""
        if seconds < 0:  # Running timer has negative duration
            return "In progress"
        
        # Create a timedelta and format it
        duration = timedelta(seconds=seconds)
        hours, remainder = divmod(duration.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        return f"{hours}h {minutes}m {seconds}s"

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
                return (json.dumps({'message': 'No time entries found'}), 200, headers)
            else:
                # Format the time entries for response
                formatted_entries = []
                
                for entry in time_entries:
                    # Convert timestamps to readable format
                    start_time = "Unknown"
                    if "start" in entry and entry["start"]:
                        try:
                            start_time = datetime.fromisoformat(entry["start"].replace("Z", "+00:00"))
                            start_time = start_time.strftime("%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            pass
                    
                    # Handle entries that are still running (no stop time)
                    stop_time = "Not stopped"
                    if "stop" in entry and entry["stop"]:
                        try:
                            stop_time = datetime.fromisoformat(entry["stop"].replace("Z", "+00:00"))
                            stop_time = stop_time.strftime("%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            pass
                    
                    # Format duration
                    duration = "Unknown"
                    if "duration" in entry:
                        duration = format_duration(entry["duration"])
                    
                    # Format entry
                    formatted_entry = {
                        'description': entry.get('description', 'No description'),
                        'project_id': entry.get('project_id', 'No project'),
                        'start': start_time,
                        'stop': stop_time,
                        'duration': duration
                    }
                    
                    formatted_entries.append(formatted_entry)
                
                return (json.dumps({'entries': formatted_entries}), 200, headers)
        else:
            return (json.dumps({'error': f'Error accessing Toggl API: {response.status_code}'}), 500, headers)

    except requests.exceptions.RequestException as e:
        return (json.dumps({'error': f'Request failed: {str(e)}'}), 500, headers)
    except json.JSONDecodeError:
        return (json.dumps({'error': 'Failed to parse the API response as JSON'}), 500, headers)
    except Exception as e:
        return (json.dumps({'error': f'An error occurred: {str(e)}'}), 500, headers)