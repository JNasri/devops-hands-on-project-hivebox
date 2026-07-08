# HiveBox - A versatile application framework for
# building modular and scalable applications.
# @author: Youssef Nasri

# datetime : used to calcluate the 1-hour window requirmenets
from datetime import datetime, timedelta, timezone

# flask : web app runtime env + jsonify to return json files
from flask import Flask, Response, jsonify

# requests : library to send HTTP requests
import requests

# detenv: used to get env vars from .env file
from dotenv import dotenv_values

# prometheus client to measure metrics from our application
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    generate_latest,
    Histogram,
)

# Load .env file into a dictionary called config
config = dotenv_values(".env")

# create instance of Flask class using the default module __name__
app = Flask(__name__)

# Version follows Semantic Versioning (SemVer)
__version__ = "0.0.1"


# Define Prometheus Metrics
metric_fetch_counter = Counter(
    "metric_fetch_counter",
    "Number of times /metric was fetched",
)


@app.route("/metrics", methods=["GET"])
def get_prometheus_metrics():
    """Return Prometheus-formatted metrics for the application."""
    metric_fetch_counter.inc()
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


# Define Metrics
version_fetch_counter = Counter(
    "version_fetch_counter",
    "Number of times /version was fetched",
)


@app.route("/version")
def print_version():
    """Return the current application version."""
    version_fetch_counter.inc()
    return __version__


# Define Metrics that will be monitored and show them in /metrics
temp_fetch_counter = Counter(
    "temp_fetch_counter",
    "Number of times /temperature was fetched",
)

temp_fetch_duration = Histogram(
    "temp_fetch_duration",
    "Time taken to proccess /temperature",
)


@app.route("/temperature", methods=["GET"])
def get_average_temperature():
    """Fetch temperature measurements and calculate the global average."""
    temp_fetch_counter.inc()

    with temp_fetch_duration.time():
        try:
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(hours=1)

            query_params = {
                "phenomenon": config.get("TEMPERATURE_PHENOMENON", "Temperatur"),
                "bbox": config.get("TEMPERATURE_BBOX", "5.5,47.2,15.2,55.1"),
                "from-date": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "to-date": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "format": "json",
            }

            response = requests.get(
                config.get(
                    "TEMPERATURE_API_URL",
                    "https://api.opensensemap.org/boxes/data",
                ),
                params=query_params,
                timeout=30,
            )
            response.raise_for_status()

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

            global_average = round(sum(valid_temperatures) / len(valid_temperatures), 2)

            return jsonify(
                {
                    "average_temperature": global_average,
                    "unit": config.get("TEMPERATURE_UNIT", "°C"),
                    "active_sensors_calculated": len(valid_temperatures),
                    "time_window_checked": "Past 1 hour",
                    "status": (
                        "Too Cold"
                        if global_average <= 10
                        else "Good"
                        if global_average < 36
                        else "Too Hot"
                    ),
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
