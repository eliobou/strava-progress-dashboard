# Use an official lightweight Python image
FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the scripts (at the end to preserve pip cache if possible)
COPY scripts/strava_sync.py .

# Define the default entry point
CMD ["python", "strava_sync.py"]
