from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
import datetime
import os

# InfluxDB configuration
INFLUXDB_URL = os.getenv("INFLUXDB_URL")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN")
ORG = os.getenv("INFLUXDB_ORG")
BUCKET = os.getenv("INFLUXDB_BUCKET")

# Checking env variables
if not all([INFLUXDB_URL, INFLUXDB_TOKEN, ORG, BUCKET]):
    raise EnvironmentError("One or more environment variables are missing.")

# Connection to InfluxDB
client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=ORG)
write_api = client.write_api(write_options=SYNCHRONOUS)

# Begining and ending dates
start_date = datetime.date(2025, 1, 1)
end_date = datetime.date(2025, 12, 31)

# Day number calculation
def get_day_of_year(date):
    return date.timetuple().tm_yday

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

    print("Day " + str(day_number) + " inserted")

print("All data inserted with success!")