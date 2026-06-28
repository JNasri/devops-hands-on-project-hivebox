# HiveBox - A versatile application framework for
# building modular and scalable applications.
# @author: Youssef Nasri

from datetime import datetime, timedelta, timezone

import requests
from flask import Flask, jsonify

# Version follows Semantic Versioning (SemVer)
__version__ = "0.0.1"

# create instance of Flask class using the default module __name__
app = Flask(__name__)

# URL for openSenseMap query endpoint
SENSORS_DATA_URL = "https://api.opensensemap.org/boxes/data"


@app.route("/version")
def print_version():
    """Return the current application version."""
    return __version__


@app.route("/temperature", methods=["GET"])
def get_average_temperature():
    """Fetch temperature measurements and calculate the global average."""
    try:
        # 1. Define our 1-hour expiration window in UTC
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=1)

        # 2. Build parameter queries for openSenseMap.
        # Wide bbox bounding box filter (e.g. Central Europe).
        # This reduces data size so the openSenseMap API returns clean JSON
        # instead of massive CSV text.
        query_params = {
            "phenomenon": "Temperatur",
            "bbox": "5.5,47.2,15.2,55.1",
            "from-date": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to-date": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "format": "json",
        }

        # 3. Request data payload directly
        response = requests.get(
            SENSORS_DATA_URL,
            params=query_params,
            timeout=15,
        )
        response.raise_for_status()

        # 4. Check if content type is actually JSON before parsing.
        if "application/json" not in response.headers.get("Content-Type", ""):
            return jsonify(
                {
                    "status": "error",
                    "message": (
                        "Upstream API returned raw text/CSV instead of "
                        "expected JSON structure."
                    ),
                }
            ), 502

        measurements = response.json()

        # 5. Filter and process values safely
        valid_temperatures = []

        for entry in measurements:
            if not isinstance(entry, dict):
                continue

            raw_val = entry.get("value")
            if raw_val is None:
                continue

            try:
                valid_temperatures.append(float(raw_val))
            except (ValueError, TypeError):
                continue

        # 6. Handle empty dataset scenario
        if not valid_temperatures:
            return jsonify(
                {
                    "status": "error",
                    "message": (
                        "No valid temperature readings found within the "
                        "last 1 hour inside this region."
                    ),
                }
            ), 503

        # 7. Compute mathematical average
        global_average = sum(valid_temperatures) / len(valid_temperatures)

        return jsonify(
            {
                "average_temperature": round(global_average, 2),
                "unit": "°C",
                "active_sensors_calculated": len(valid_temperatures),
                "time_window_checked": "Past 1 hour",
            }
        ), 200

    except requests.exceptions.RequestException as exc:
        return jsonify(
            {
                "error": "Failed to connect to openSenseMap platform",
                "details": str(exc),
            }
        ), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
