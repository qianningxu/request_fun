import os
import requests
import base64
import json
from datetime import datetime, time, timedelta
import pytz # For timezone handling
from flask import Flask, request, jsonify

# Initialize Flask app
app = Flask(__name__)

# --- CONFIGURATION ---
# HARDCODED Toggl API Token (Not Recommended for Security)
HARDCODED_TOGGL_API_TOKEN = "cf35eb86aa00bfe5321d778fcf40d5a8"

# Environment variable name for optional function access secret
FUNCTION_SECRET_ENV_VAR = "FUNCTION_SECRET"

# Toggl API v9 Base URL
TOGGL_API_BASE = "https://api.track.toggl.com/api/v9"

# --- Helper Functions ---

def get_toggl_auth_header(api_token):
    """Creates the Basic Auth header needed for Toggl API v9."""
    if not api_token:
        raise ValueError("API token is missing")
    credentials = f"{api_token}:api_token"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    return {"Authorization": f"Basic {encoded_credentials}"}

def get_toggl_data(endpoint, api_token, params=None):
    """Fetches data from a Toggl API endpoint."""
    auth_headers = get_toggl_auth_header(api_token)

    headers = {
        "Content-Type": "application/json",
        **auth_headers
    }
    api_url = f"{TOGGL_API_BASE}{endpoint}"

    try:
        response = requests.get(api_url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        error_detail = f"Toggl API returned status {response.status_code}"
        try:
             error_content = response.json()
             error_detail += f": {json.dumps(error_content)}"
        except (ValueError, json.JSONDecodeError):
             error_detail += f": {response.text}"
        print(f"ERROR: HTTP error occurred calling {endpoint}: {http_err}")
        raise ConnectionError(f"Toggl API request failed: {error_detail}")

    except requests.exceptions.RequestException as req_err:
        print(f"ERROR: Request exception occurred calling {endpoint}: {req_err}")
        raise ConnectionError(f"Toggl API connection failed: {req_err}")
    except Exception as e:
        print(f"ERROR: Unexpected error during Toggl request to {endpoint}: {e}")
        raise ValueError(f"Unexpected error during API request: {e}")


def parse_toggl_datetime(datetime_str):
    """Parses Toggl's ISO 8601 datetime strings, handling potential Z suffix and ensuring timezone awareness."""
    if not datetime_str:
        return None
    try:
        if datetime_str.endswith('Z'):
            datetime_str = datetime_str[:-1] + '+00:00'
        dt = datetime.fromisoformat(datetime_str)
        if dt.tzinfo is None:
             print(f"WARN: Parsed datetime without timezone info: {datetime_str}. Assuming UTC.")
             return pytz.utc.localize(dt)
        return dt
    except ValueError:
        print(f"WARN: Could not parse datetime string: {datetime_str}")
        return None

def calculate_duration(entry, now_utc):
    """Calculates duration in seconds, handling running timers using timezone-aware comparison."""
    duration = entry.get('duration', 0)
    if duration < 0:
        start_time = parse_toggl_datetime(entry.get('start'))
        if start_time:
            if now_utc.tzinfo is None:
                 print("ERROR: now_utc lacks timezone info in calculate_duration")
                 now_utc = pytz.utc.localize(datetime.utcnow())
            duration = (now_utc - start_time).total_seconds()
        else:
            duration = 0
    return max(0, duration)

# --- Main Function Logic ---

@app.route('/', methods=['GET', 'POST'])
def check_play_time_allowance():
    """
    Checks if requested play time is allowed based on Toggl focus/play entries.
    Expects 'play_time' query parameter (integer, minutes).
    """
    # 1. --- Security Header Check (Optional but Recommended) ---
    expected_secret = os.environ.get(FUNCTION_SECRET_ENV_VAR)
    if expected_secret:
        received_secret = request.headers.get("X-Function-Secret")
        if received_secret != expected_secret:
            print("WARN: Unauthorized attempt denied (Secret Header mismatch).")
            return jsonify({"error": "Unauthorized"}), 403
        else:
             print("INFO: Authorized via function secret header.")

    toggl_api_token = HARDCODED_TOGGL_API_TOKEN # Using hardcoded token

    # 2. --- Input Validation ---
    try:
        requested_play_time_min = request.args.get('play_time', type=int)
        if requested_play_time_min is None or requested_play_time_min < 0:
            print("ERROR: Missing or invalid 'play_time' query parameter.")
            return jsonify({"error": "Missing or invalid 'play_time' query parameter (must be a non-negative integer in minutes)"}), 400
    except ValueError:
         print("ERROR: Non-integer 'play_time' query parameter.")
         return jsonify({"error": "Invalid 'play_time' query parameter (must be an integer)"}), 400

    print(f"INFO: Received request for play_time={requested_play_time_min} minutes.")

    # 3. --- Get User Info and Calculate Time Ranges ---
    try:
        user_info = get_toggl_data("/me", toggl_api_token)
        user_timezone_str = user_info.get('timezone')
        if not user_timezone_str:
             print("ERROR: Could not retrieve timezone from Toggl /me endpoint.")
             return jsonify({"error": "Configuration error: Failed to get user timezone"}), 500

        user_tz = pytz.timezone(user_timezone_str)
        print(f"INFO: User timezone detected: {user_timezone_str}")

        now_local = datetime.now(user_tz)
        now_utc = now_local.astimezone(pytz.utc)

        today_4am_local = now_local.replace(hour=4, minute=0, second=0, microsecond=0)
        if now_local.time() < time(4, 0):
             today_4am_local -= timedelta(days=1)

        start_of_week_local = now_local - timedelta(days=now_local.weekday())
        start_of_week_local = start_of_week_local.replace(hour=0, minute=0, second=0, microsecond=0)

        today_4am_utc_iso = today_4am_local.astimezone(pytz.utc).isoformat(timespec='seconds')
        start_of_week_utc_iso = start_of_week_local.astimezone(pytz.utc).isoformat(timespec='seconds')
        now_utc_iso = now_utc.isoformat(timespec='seconds')

        print(f"INFO: Time range for today's focus check (UTC): {today_4am_utc_iso} to {now_utc_iso}")
        print(f"INFO: Time range for weekly check (UTC): {start_of_week_utc_iso} to {now_utc_iso}")

    except pytz.UnknownTimeZoneError:
        print(f"ERROR: Unknown timezone identifier: {user_timezone_str}")
        return jsonify({"error": "Configuration error: Invalid timezone received"}), 500
    except (ConnectionError, ValueError, Exception) as e:
        print(f"ERROR: Failed getting user info or calculating times: {e}")
        status_code = 502 if isinstance(e, ConnectionError) else 500
        return jsonify({"error": "Failed to initialize", "details": str(e)}), status_code

    # 4. --- "Today's Focus" Check ---
    try:
        print(f"INFO: Fetching entries since {today_4am_utc_iso} for today's focus check...")
        params_today = {"start_date": today_4am_utc_iso, "end_date": now_utc_iso}
        todays_entries = get_toggl_data("/me/time_entries", toggl_api_token, params=params_today)
        if todays_entries is None: todays_entries = []
        if not isinstance(todays_entries, list):
             print(f"WARN: Expected list for today's entries, got {type(todays_entries)}. Treating as empty.")
             todays_entries = []

        print(f"INFO: Received {len(todays_entries)} entries for today's check.")
        todays_focus_duration_sec = 0
        for entry in todays_entries:
            tags = entry.get('tags', [])
            if "专注" in tags:
                duration = calculate_duration(entry, now_utc)
                todays_focus_duration_sec += duration

        todays_focus_duration_min = todays_focus_duration_sec / 60
        print(f"INFO: Today's total focus duration: {todays_focus_duration_min:.2f} minutes")

        if todays_focus_duration_min < 90:
            print("INFO: Condition unmet: Today's focus < 90 min.")
            return jsonify({"allowed": False, "message": "Not enough focus has done today to earn you the right to play"})
        else:
            print("INFO: Condition met: Today's focus >= 90 min.")

    except (ConnectionError, ValueError, Exception) as e:
        print(f"ERROR: Failed during today's focus check: {e}")
        status_code = 502 if isinstance(e, ConnectionError) else 500
        return jsonify({"error": "Failed processing today's entries", "details": str(e)}), status_code

    # 5. --- "Weekly Balance" Check (only if today's focus > 90 min) ---
    try:
        print(f"INFO: Fetching entries since {start_of_week_utc_iso} for weekly balance check...")
        params_week = {"start_date": start_of_week_utc_iso, "end_date": now_utc_iso}
        weekly_entries = get_toggl_data("/me/time_entries", toggl_api_token, params=params_week)
        if weekly_entries is None: weekly_entries = []
        if not isinstance(weekly_entries, list):
             print(f"WARN: Expected list for weekly entries, got {type(weekly_entries)}. Treating as empty.")
             weekly_entries = []

        print(f"INFO: Received {len(weekly_entries)} entries for weekly check.")
        total_focus_sec = 0
        total_play_sec = 0
        for entry in weekly_entries:
            tags = entry.get('tags', [])
            duration_sec = calculate_duration(entry, now_utc)
            if "专注" in tags:
                total_focus_sec += duration_sec
            if "娱乐" in tags:
                total_play_sec += duration_sec

        total_focus_min = total_focus_sec / 60
        total_play_min = total_play_sec / 60
        print(f"INFO: Weekly total focus duration: {total_focus_min:.2f} minutes")
        print(f"INFO: Weekly total play duration: {total_play_min:.2f} minutes")
        print(f"INFO: Requested play time: {requested_play_time_min} minutes")

        threshold = total_focus_min * 0.5
        potential_total_play = total_play_min + requested_play_time_min
        print(f"INFO: Checking if {potential_total_play:.2f} (play) > {threshold:.2f} (focus * 0.5)")

        if potential_total_play > threshold:
            print("INFO: Condition unmet: Weekly play ratio exceeded.")
            return jsonify({"allowed": False, "message": "Too much play time this week"})
        else:
            print("INFO: Condition met: Weekly play ratio allows requested time.")
            return jsonify({"allowed": True, "message": f"A play time of {requested_play_time_min} minutes is permitted"})

    except (ConnectionError, ValueError, Exception) as e:
        print(f"ERROR: Failed during weekly balance check: {e}")
        status_code = 502 if isinstance(e, ConnectionError) else 500
        return jsonify({"error": "Failed processing weekly entries", "details": str(e)}), status_code

# Note: The Gunicorn server specified in Procfile will run the 'app' object.
# The __main__ block below is only for direct local execution (python main.py)
# and won't be used by Cloud Run via Gunicorn/Procfile.
# if __name__ == "__main__":
#     # This block is NOT used by Cloud Run with Gunicorn/Procfile
#     # For local testing, you'd typically run: gunicorn -b localhost:8080 main:app
#     print("Starting Flask development server (for local testing only)...")
#     app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))