import functions_framework
import requests
import json
from datetime import datetime, timedelta
import pytz

@functions_framework.http
def request_fun(request):
    """HTTP Cloud Function to retrieve Toggl time entries and validate play time.
    Args:
        request (flask.Request): The request object with 'requested_play_time' parameter.
    Returns:
        The response text with play time decision.
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
    
    # Get the requested_play_time parameter
    # Check if it's in query parameters
    requested_play_time = request.args.get('requested_play_time')
    
    # If not in query params, check if it's in JSON body
    if not requested_play_time and request.is_json:
        request_json = request.get_json(silent=True)
        if request_json and 'requested_play_time' in request_json:
            requested_play_time = request_json['requested_play_time']
    
    # Validate requested_play_time
    try:
        if not requested_play_time:
            return (json.dumps({'error': 'requested_play_time parameter is required'}), 400, headers)
        requested_play_time = int(requested_play_time)
    except ValueError:
        return (json.dumps({'error': 'requested_play_time must be a number'}), 400, headers)
    
    # API credentials
    api_token = "cf35eb86aa00bfe5321d778fcf40d5a8"
    
    # Helper function to convert seconds to minutes
    def seconds_to_minutes(seconds):
        if seconds < 0:  # Running timer has negative duration
            return 0
        return seconds / 60
    
    # Helper function to check if a date is today after 4am
    def is_today_after_4am(timestamp):
        # Get current timezone-aware datetime
        now = datetime.now(pytz.UTC)
        
        # Create today at 4am
        today_4am = datetime.combine(now.date(), datetime.min.time())
        today_4am = today_4am.replace(hour=4, tzinfo=pytz.UTC)
        
        # Convert timestamp to datetime object
        try:
            entry_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            return False
            
        return entry_time >= today_4am
    
    # Helper function to check if a date is from Monday of this week
    def is_from_monday_this_week(timestamp):
        # Get current timezone-aware datetime
        now = datetime.now(pytz.UTC)
        
        # Calculate Monday of current week
        days_since_monday = now.weekday()
        monday = now - timedelta(days=days_since_monday)
        monday = datetime.combine(monday.date(), datetime.min.time())
        monday = monday.replace(tzinfo=pytz.UTC)
        
        # Convert timestamp to datetime object
        try:
            entry_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            return False
            
        return entry_time >= monday
    
    # API endpoint for time entries
    base_url = "https://api.track.toggl.com/api/v9"
    time_entries_endpoint = f"{base_url}/me/time_entries"

    try:
        # Make the API request to get time entries
        # Get more entries to ensure we have enough data for the week
        response = requests.get(
            time_entries_endpoint,
            auth=(api_token, "api_token"),
            params={"limit": 100}  # Increased limit to get more entries
        )
        
        # Check if the request was successful
        if response.status_code == 200:
            # Parse the JSON response
            time_entries = response.json()
            
            if not time_entries:
                return (json.dumps({'message': 'No time entries found'}), 200, headers)
            
            # STEP 1: Process today's focus time entries
            today_focus_entries = [
                entry for entry in time_entries 
                if entry.get("start") and is_today_after_4am(entry["start"]) and 
                any(tag == "专注" for tag in entry.get("tags", []))
            ]
            
            # Calculate total focus duration today in minutes
            today_focus_minutes = sum(
                seconds_to_minutes(entry["duration"]) 
                for entry in today_focus_entries 
                if "duration" in entry and entry["duration"] is not None
            )
            
            # Check if there's enough focus time today
            if today_focus_minutes < 90:
                return (json.dumps({
                    'result': 'denied',
                    'message': 'Not enough focus has been done today to earn you the right to play',
                    'today_focus_minutes': today_focus_minutes
                }), 200, headers)
            
            # STEP 2: Process this week's entries
            weekly_entries = [
                entry for entry in time_entries 
                if entry.get("start") and is_from_monday_this_week(entry["start"])
            ]
            
            # Calculate total focus and play time for the week
            total_focus_minutes = sum(
                seconds_to_minutes(entry["duration"]) 
                for entry in weekly_entries 
                if "duration" in entry and entry["duration"] is not None and
                any(tag == "专注" for tag in entry.get("tags", []))
            )
            
            total_play_minutes = sum(
                seconds_to_minutes(entry["duration"]) 
                for entry in weekly_entries 
                if "duration" in entry and entry["duration"] is not None and
                any(tag == "娱乐" for tag in entry.get("tags", []))
            )
            
            # Apply the play time rule
            if (total_play_minutes + requested_play_time) > (total_focus_minutes * 0.5):
                return (json.dumps({
                    'result': 'denied',
                    'message': 'Too much play time this week',
                    'total_focus_minutes': total_focus_minutes,
                    'total_play_minutes': total_play_minutes,
                    'play_time_limit': total_focus_minutes * 0.5,
                    'remaining_play_time': max(0, (total_focus_minutes * 0.5) - total_play_minutes)
                }), 200, headers)
            else:
                return (json.dumps({
                    'result': 'permitted',
                    'message': f'A play time of {requested_play_time} minutes is permitted',
                    'total_focus_minutes': total_focus_minutes,
                    'total_play_minutes': total_play_minutes,
                    'play_time_limit': total_focus_minutes * 0.5,
                    'remaining_play_time': (total_focus_minutes * 0.5) - total_play_minutes
                }), 200, headers)
                
        else:
            return (json.dumps({'error': f'Error accessing Toggl API: {response.status_code}'}), 500, headers)

    except requests.exceptions.RequestException as e:
        return (json.dumps({'error': f'Request failed: {str(e)}'}), 500, headers)
    except json.JSONDecodeError:
        return (json.dumps({'error': 'Failed to parse the API response as JSON'}), 500, headers)
    except Exception as e:
        return (json.dumps({'error': f'An error occurred: {str(e)}'}), 500, headers)