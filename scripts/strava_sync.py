from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
import requests
import datetime
import time
import os

# Configuration
INFLUXDB_URL = os.getenv("INFLUXDB_URL")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN")
ORG = os.getenv("INFLUXDB_ORG")
BUCKET = os.getenv("INFLUXDB_BUCKET")
BASE_URL = "https://www.strava.com/api/v3"

CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("STRAVA_REFRESH_TOKEN")
TOKEN_URL = "https://www.strava.com/oauth/token"

# Checking env variables
if not all([INFLUXDB_URL, INFLUXDB_TOKEN, ORG, BUCKET, BASE_URL, CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN, TOKEN_URL]):
    raise EnvironmentError("One or more environment variables are missing.")

# Retrieve token from Strava
def get_access_token():
    response = requests.post(TOKEN_URL, data={
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'refresh_token': REFRESH_TOKEN,
        'grant_type': 'refresh_token'
    })
    response.raise_for_status()
    return response.json()['access_token']

# Check if the activity already exists in the InfluxDB
def day_numbers_exists(client, year):
    query_api = client.query_api()
    query = f'''from(bucket: "{BUCKET}") 
                    |> range(start: 0) 
                    |> filter(fn: (r) => r._measurement == "day_numbers" and 
                                         r._field == "day_number" and 
                                         r.year == {year})'''
    result = query_api.query(org=ORG, query=query)
    return len(result) > 0  # True if the day_numbers already exists

# Day number calculation
def get_day_of_year(date):
    return date.timetuple().tm_yday

def write_day_numbers(year):
    # Connection to InfluxDB
    client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=ORG)
    write_api = client.write_api(write_options=SYNCHRONOUS)
    
    # Begining and ending dates
    start_date = datetime.date(year, 1, 1)
    end_date = datetime.date(year, 12, 31)

    # Writing to InfluxDB for every day
    for single_date in (start_date + datetime.timedelta(n) for n in range((end_date - start_date).days + 1)):
        day_number = get_day_of_year(single_date)

        # Convert `datetime.date` to `datetime.datetime` while fixing hour to 00:00:00
        datetime_obj = datetime.datetime(single_date.year, single_date.month, single_date.day, 0, 0, 0)
        
        point = Point("day_numbers") \
            .tag("year", str(single_date.year)) \
            .field("day_number", day_number) \
            .time(datetime_obj, WritePrecision.NS)  # Use WritePrecision.NS
        
        # Writing in InfluxDB bucket
        write_api.write(bucket=BUCKET, org=ORG, record=point)

        print(f"Day {day_number} inserted")

    print("All day numberq inserted with success!")

# Check if the day numbers of the year exists in the InfluxDB
def activity_exists(client, activity_id):
    query_api = client.query_api()
    query = f'''from(bucket: "{BUCKET}") 
                    |> range(start: 0) 
                    |> filter(fn: (r) => r._measurement == "activities" and 
                                         r._field == "id" and 
                                         r._value == {activity_id})'''
    result = query_api.query(org=ORG, query=query)
    return len(result) > 0  # True if the ID already exists

# Get all activity IDs stored in InfluxDB for a given year
def get_stored_activity_ids(client, year):
    start_date = datetime.datetime(year, 1, 1).isoformat() + "Z"
    end_date = datetime.datetime(year, 12, 31, 23, 59, 59).isoformat() + "Z"
    
    query_api = client.query_api()
    query = f'''
    from(bucket: "{BUCKET}")
        |> range(start: {start_date}, stop: {end_date})
        |> filter(fn: (r) => r._measurement == "activities" and r._field == "id")
        |> group()
        |> distinct(column: "_value")
    '''
    
    result = query_api.query(org=ORG, query=query)
    activity_ids = []
    
    for table in result:
        for record in table.records:
            activity_ids.append(int(record.get_value()))
    
    return activity_ids

# Delete an activity from InfluxDB by ID
def delete_activity(client, activity_id):
    delete_api = client.delete_api()
    
    predicate = f'_measurement="activities" AND id="{activity_id}"'
    
    try:
        # Use start and end over a sufficiently large range
        start_time = "2010-01-01T00:00:00Z"
        end_time = "2040-01-01T00:00:00Z"
        
        delete_api.delete(start_time, end_time, predicate, bucket=BUCKET, org=ORG)
        print(f"Activity {activity_id} deleted from InfluxDB.")
        return True
    except Exception as e:
        print(f"Error deleting activity {activity_id}: {str(e)}")
        return False

# Synchronize activities
def sync_activities(access_token, year):
    headers = {"Authorization": f"Bearer {access_token}"}
    after = int(datetime.datetime(year, 1, 1).timestamp())
    before = int(datetime.datetime(year, 12, 31).timestamp())
    page = 1
    
    # List to store Strava activity IDs
    strava_activity_ids = []

    with InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=ORG) as client:
        write_api = client.write_api(write_options=SYNCHRONOUS)

        # Retrieve all activities from Strava for the given year
        while True:
            try:
                print(f"Fetching page {page} of activities...")
                response = requests.get(
                    f"{BASE_URL}/athlete/activities",
                    headers=headers,
                    params={"page": page, "per_page": 200, "after": after, "before": before}
                )
                response.raise_for_status()
                activities = response.json()

                if not activities:
                    print(f"No more activities found after page {page-1}")
                    break

                print(f"Retrieved {len(activities)} activities")
                for activity in activities:
                    activity_id = activity["id"]
                    strava_activity_ids.append(activity_id)
                    
                    # Check if the activity already exists
                    if activity_exists(client, activity_id) == False:
                        # New activity, add it
                        point = create_activity_point(activity)
                        write_api.write(bucket=BUCKET, org=ORG, record=point)
                        print(f"Activity {activity_id} added.")

                page += 1
            except Exception as e:
                print(f"Error retrieving activities page {page}: {str(e)}")
                break
        
        # Debug info
        print(f"Retrieved {len(strava_activity_ids)} activities from Strava")
        
        # Get all activity IDs stored in InfluxDB for the given year
        stored_activity_ids = get_stored_activity_ids(client, year)
        print(f"Found {len(stored_activity_ids)} activities in InfluxDB")
        
        # Convert lists to sets for easier comparison
        strava_ids_set = set(strava_activity_ids)
        stored_ids_set = set(stored_activity_ids)
        
        # Display IDs for debugging
        if len(stored_ids_set) < 10:  # Limit output if too many
            print(f"Stored IDs: {stored_ids_set}")
        if len(strava_ids_set) < 10:
            print(f"Strava IDs: {strava_ids_set}")
        
        # Identify activities to delete (those in InfluxDB but not in Strava)
        activities_to_delete = stored_ids_set - strava_ids_set
        print(f"Found {len(activities_to_delete)} activities to delete")
        
        # Delete activities that no longer exist in Strava
        for stored_id in activities_to_delete:
            print(f"Activity {stored_id} no longer exists in Strava, deleting...")
            delete_activity(client, stored_id)

    print("Synchronization complete.")

# Create an InfluxDB point for an activity
def create_activity_point(activity):
    activity_id = activity["id"]
    commute_value = str(int(activity.get("commute", False)))
    
    try:
        start_date_str = activity["start_date"]
        start_time = datetime.datetime.strptime(start_date_str, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        # Handle different date format if needed
        try:
            start_time = datetime.datetime.strptime(start_date_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        except ValueError:
            # Fallback to current time if parsing fails
            start_time = datetime.datetime.now(datetime.timezone.utc)
            print(f"Warning: Could not parse date '{start_date_str}' for activity {activity_id}, using current time.")
    
    point = Point("activities") \
        .tag("type", activity["type"]) \
        .tag("id", str(activity_id)) \
        .tag("commute", commute_value) \
        .field("id", activity_id) \
        .field("distance", activity["distance"]) \
        .field("moving_time", activity["moving_time"]) \
        .field("elapsed_time", activity["elapsed_time"]) \
        .field("total_elevation_gain", activity["total_elevation_gain"]) \
        .field("average_speed", activity["average_speed"]) \
        .field("max_speed", activity["max_speed"]) \
        .field("start_latlng", str(activity.get("start_latlng", []))) \
        .field("end_latlng", str(activity.get("end_latlng", []))) \
        .field("start_date", activity["start_date"]) \
        .field("start_date_local", activity["start_date_local"]) \
        .field("commute", bool(activity.get("commute", False))) \
        .time(start_time, WritePrecision.NS)
    
    return point

# Check InfluxDB configuration and permissions
def check_influx_connection():
    try:
        with InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=ORG) as client:
            health = client.health()
            print(f"InfluxDB connection: {health.status}")
            
            buckets_api = client.buckets_api()
            bucket_list = buckets_api.find_buckets().buckets
            bucket_names = [bucket.name for bucket in bucket_list]
            
            if BUCKET in bucket_names:
                print(f"Bucket '{BUCKET}' exists.")
            else:
                print(f"Bucket '{BUCKET}' not found. Available buckets: {bucket_names}")
            
            return True
    except Exception as e:
        print(f"InfluxDB connection error: {str(e)}")
        return False

# Main
if __name__ == "__main__":
    print("Checking InfluxDB connection...")
    if check_influx_connection():
        print("Connection successful.")
        
        print("Checking if day numbers exists in InfluxDB...")
        if day_numbers_exists():
            print("Day numbers exists in InfluxDB, proceeding with sync...")
        else:
            write_day_numbers(2025)

        token = get_access_token()
        sync_activities(token, 2025)
    else:
        print("Failed to connect to InfluxDB. Please check your configuration.")
