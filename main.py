# HiveBox - A versatile application framework for
# building modular and scalable applications.
# @author: Youssef Nasri

# datetime : used to calcluate the 1-hour window requirmenets
from datetime import datetime, timedelta, timezone

import io
import json
import os
import threading
import time

# minio: used to store data in minio local object storage
from minio import Minio

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


# Load .env file and allow container environment variables to override it.
dotenv_config = {
    key: value for key, value in dotenv_values(".env").items() if value is not None
}
env_config = {
    key: value
    for key, value in os.environ.items()
    if key.startswith(("TEMPERATURE_", "MINIO_"))
}
config = {**dotenv_config, **env_config}

# create instance of Flask class using the default module __name__
app = Flask(__name__)

# Version follows Semantic Versioning (SemVer)
__version__ = "0.0.1"


# Define Prometheus for /metrics
metric_fetch_counter = Counter(
    "metric_fetch_counter",
    "Number of times /metric was fetched",
)

@app.route("/metrics", methods=["GET"])
def get_prometheus_metrics():
    """Return Prometheus-formatted metrics for the application."""
    metric_fetch_counter.inc()
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


# Define Metrics for /version endpoint
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

def get_temperature_snapshot():
    """Call openSenseMap and return a computed temperature snapshot."""
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
        raise ValueError("No valid temperature readings found")

    global_average = round(sum(valid_temperatures) / len(valid_temperatures), 2)

    status = "Unknown"
    if global_average < 10:
        status = "Too Cold"
    elif global_average < 36:
        status = "Good"
    else:
        status = "Too Hot"

    return {
        "average_temperature": global_average,
        "unit": config.get("TEMPERATURE_UNIT", "°C"),
        "active_sensors_calculated": len(valid_temperatures),
        "time_window_checked": "Past 1 hour",
        "status": status,
    }


@app.route("/temperature", methods=["GET"])
def get_average_temperature():
    """Fetch temperature measurements and calculate the global average."""
    temp_fetch_counter.inc()

    with temp_fetch_duration.time():
        try:
            snapshot = get_temperature_snapshot()
            return jsonify(snapshot), 200
        except requests.exceptions.RequestException as exc:
            return jsonify(
                {
                    "error": "Failed to connect to openSenseMap platform",
                    "details": str(exc),
                }
            ), 502
        except ValueError as exc:
            return jsonify({"status": "error", "message": str(exc)}), 503

def upload_snapshot_to_minio(snapshot):
    """Upload the temperature snapshot to MinIO object storage."""
    client = Minio(
        config.get("MINIO_ENDPOINT", "localhost:9000"),
        access_key=config.get("MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=config.get("MINIO_SECRET_KEY", "minioadmin"),
        secure=False,
    )

    bucket = config.get("MINIO_BUCKET", "hivebox")
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)

    object_name = f"temperature/{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%S')}.json"
    data = json.dumps(snapshot).encode("utf-8")
    client.put_object(bucket, object_name, io.BytesIO(data), len(data))

@app.route("/store", methods=["POST"])
def store_data():
    """Trigger a data storage operation."""
    try:
        snapshot = get_temperature_snapshot()
        snapshot["timestamp"] = datetime.now(timezone.utc).isoformat()
        upload_snapshot_to_minio(snapshot)
    except Exception as exc:
        return jsonify({"message": "Snapshot storage failed", "error": str(exc)}), 502

    return jsonify({"message": "Snapshot stored successfully", "data": snapshot}), 200


def periodic_store():
    """Store one snapshot immediately and then every 5 minutes."""
    while True:
        try:
            snapshot = get_temperature_snapshot()
            snapshot["timestamp"] = datetime.now(timezone.utc).isoformat()
            upload_snapshot_to_minio(snapshot)
            print("Periodic store executed:", snapshot)
        except Exception as exc:
            print("Periodic store failed:", exc)
        time.sleep(300)


threading.Thread(target=periodic_store, daemon=True).start()

# Trigger the first periodic save immediately on startup.
try:
    snapshot = get_temperature_snapshot()
    snapshot["timestamp"] = datetime.now(timezone.utc).isoformat()
    upload_snapshot_to_minio(snapshot)
except Exception as exc:
    print("Initial store failed:", exc)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
