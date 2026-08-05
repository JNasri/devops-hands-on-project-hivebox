"""HiveBox API and web application."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import io
import json
import logging
import math
import os
import sys
import threading
import time
from uuid import uuid4

from dotenv import dotenv_values
from flask import Flask, Response, jsonify, render_template, request
from minio import Minio
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from redis import Redis
from redis.exceptions import RedisError
import requests
from werkzeug.middleware.proxy_fix import ProxyFix


logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("hivebox")

dotenv_config = {
    key: value
    for key, value in dotenv_values(".env").items()
    if value is not None
}
env_config = {
    key: value
    for key, value in os.environ.items()
    if key.startswith(
        (
            "APP_",
            "API_",
            "LOG_",
            "MINIO_",
            "NOMINATIM_",
            "STORE_",
            "TEMPERATURE_",
            "VALKEY_",
        )
    )
}
config = {**dotenv_config, **env_config}

app = Flask(__name__)
if config.get("APP_TRUST_PROXY", "false").lower() in {"1", "true", "yes"}:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
__version__ = "1.0.0"

cache = Redis.from_url(
    config.get("VALKEY_URL", "redis://localhost:6379"),
    decode_responses=True,
    socket_connect_timeout=1,
    socket_timeout=1,
)


metric_fetch_counter = Counter(
    "hivebox_metrics_requests_total",
    "Number of requests to the metrics endpoint",
)
version_fetch_counter = Counter(
    "hivebox_version_requests_total",
    "Number of requests to the version endpoint",
)
temperature_fetch_counter = Counter(
    "hivebox_temperature_requests_total",
    "Number of temperature requests",
    ["scope"],
)
temperature_fetch_duration = Histogram(
    "hivebox_temperature_request_duration_seconds",
    "Time spent serving temperature requests",
    ["scope"],
)
store_counter = Counter(
    "hivebox_store_operations_total",
    "Number of snapshot storage operations",
    ["trigger", "result"],
)
cache_counter = Counter(
    "hivebox_cache_operations_total",
    "Number of cache operations",
    ["operation", "result"],
)
upstream_error_counter = Counter(
    "hivebox_upstream_errors_total",
    "Number of upstream request errors",
    ["service"],
)

_nominatim_lock = threading.Lock()
_last_nominatim_request = 0.0


def get_configured_sensebox_ids():
    """Return configured senseBox IDs as a clean list."""
    raw_ids = config.get("TEMPERATURE_SENSEBOX_IDS", "")
    return [box_id.strip() for box_id in raw_ids.split(",") if box_id.strip()]


def get_request_timeout():
    """Return the upstream request timeout in seconds."""
    try:
        return max(1.0, float(config.get("TEMPERATURE_REQUEST_TIMEOUT", "15")))
    except ValueError:
        return 15.0


def get_temperature_phenomena():
    """Return configured temperature labels used by openSenseMap sensors."""
    configured = config.get("TEMPERATURE_PHENOMENA", "")
    if configured.strip():
        raw_phenomena = configured.split(",")
    else:
        raw_phenomena = [
            config.get("TEMPERATURE_PHENOMENON", "Temperatur"),
            "Temperature",
            "Temperatura",
            "Température",
            "Lufttemperatur",
        ]

    phenomena = []
    seen = set()
    for raw_phenomenon in raw_phenomena:
        phenomenon = raw_phenomenon.strip()
        normalized = phenomenon.casefold()
        if phenomenon and normalized not in seen:
            seen.add(normalized)
            phenomena.append(phenomenon)
    return phenomena or ["Temperatur"]


def cache_get_json(key):
    """Read JSON from Valkey, returning None when cache is unavailable."""
    try:
        raw_value = cache.get(key)
    except RedisError as exc:
        cache_counter.labels("get", "error").inc()
        logger.warning("Valkey read failed: %s", exc)
        return None

    if raw_value is None:
        cache_counter.labels("get", "miss").inc()
        return None

    try:
        value = json.loads(raw_value)
    except (json.JSONDecodeError, TypeError):
        cache_counter.labels("get", "invalid").inc()
        return None

    cache_counter.labels("get", "hit").inc()
    return value


def cache_set_json(key, value, ttl_seconds=None):
    """Write JSON to Valkey without making cache failure fatal."""
    try:
        cache.set(key, json.dumps(value), ex=ttl_seconds)
    except RedisError as exc:
        cache_counter.labels("set", "error").inc()
        logger.warning("Valkey write failed: %s", exc)
        return False

    cache_counter.labels("set", "success").inc()
    return True


def get_cached_snapshot():
    """Return the latest successfully cached temperature snapshot."""
    return cache_get_json("hivebox:latest_snapshot")


def get_cached_snapshot_age_seconds():
    """Return cached snapshot age, or None when missing/unavailable."""
    try:
        raw_timestamp = cache.get("hivebox:latest_snapshot_ts")
    except RedisError as exc:
        logger.warning("Valkey timestamp read failed: %s", exc)
        return None

    if raw_timestamp is None:
        return None

    try:
        age = datetime.now(timezone.utc).timestamp() - float(raw_timestamp)
        return max(0.0, age)
    except (TypeError, ValueError):
        return None


def cache_snapshot(snapshot):
    """Atomically cache the latest snapshot and its cache timestamp."""
    now_timestamp = datetime.now(timezone.utc).timestamp()
    try:
        with cache.pipeline(transaction=True) as pipeline:
            pipeline.set("hivebox:latest_snapshot", json.dumps(snapshot))
            pipeline.set("hivebox:latest_snapshot_ts", str(now_timestamp))
            pipeline.execute()
    except RedisError as exc:
        cache_counter.labels("set", "error").inc()
        logger.warning("Snapshot cache write failed: %s", exc)
        return False

    cache_counter.labels("set", "success").inc()
    return True


def temperature_status(average_temperature):
    """Map an average temperature to the HiveBox status label."""
    if average_temperature < 10:
        return "Too Cold"
    if average_temperature <= 36:
        return "Good"
    return "Too Hot"


def calculate_bbox(latitude, longitude, radius_km):
    """Create an openSenseMap bbox around a point and radius."""
    latitude_delta = radius_km / 111.32
    longitude_scale = max(math.cos(math.radians(latitude)), 0.1)
    longitude_delta = radius_km / (111.32 * longitude_scale)
    return (
        max(-180.0, longitude - longitude_delta),
        max(-90.0, latitude - latitude_delta),
        min(180.0, longitude + longitude_delta),
        min(90.0, latitude + latitude_delta),
    )


def parse_temperature_measurements(measurements):
    """Select the newest valid measurement from each sensor."""
    if not isinstance(measurements, list):
        raise ValueError("openSenseMap returned an unexpected response")

    latest_by_sensor = {}
    valid_measurement_count = 0

    for index, entry in enumerate(measurements):
        if not isinstance(entry, dict) or entry.get("value") is None:
            continue

        try:
            value = float(entry["value"])
        except (TypeError, ValueError):
            continue

        if not math.isfinite(value):
            continue

        valid_measurement_count += 1
        sensor_id = str(entry.get("sensorId") or f"unknown-{index}")
        created_at = str(entry.get("createdAt") or "")
        previous = latest_by_sensor.get(sensor_id)
        if previous is None or created_at >= previous[0]:
            latest_by_sensor[sensor_id] = (created_at, value)

    if not latest_by_sensor:
        raise ValueError("No recent temperature readings were found in this region")

    temperatures = [measurement[1] for measurement in latest_by_sensor.values()]
    newest_observation = max(
        (measurement[0] for measurement in latest_by_sensor.values()),
        default=None,
    )
    return temperatures, valid_measurement_count, newest_observation


def fetch_temperature_snapshot(bbox, region=None):
    """Fetch and summarize one hour of openSenseMap temperature data."""
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=1)
    bbox_text = ",".join(f"{coordinate:.6f}" for coordinate in bbox)
    query_params = {
        "bbox": bbox_text,
        "from-date": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "to-date": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "format": "json",
    }

    api_url = config.get(
        "TEMPERATURE_API_URL",
        "https://api.opensensemap.org/boxes/data",
    )
    phenomena = get_temperature_phenomena()
    measurements = []
    request_errors = []
    successful_requests = 0

    def fetch_phenomenon(phenomenon):
        response = requests.get(
            api_url,
            params={**query_params, "phenomenon": phenomenon},
            timeout=get_request_timeout(),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("openSenseMap returned an unexpected response")
        return payload

    workers = min(len(phenomena), 4)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(fetch_phenomenon, item) for item in phenomena]
        for future in futures:
            try:
                measurements.extend(future.result())
                successful_requests += 1
            except (requests.exceptions.RequestException, ValueError) as exc:
                request_errors.append(exc)

    if successful_requests == 0 and request_errors:
        raise request_errors[0]

    temperatures, measurement_count, newest_observation = (
        parse_temperature_measurements(measurements)
    )
    average_temperature = round(sum(temperatures) / len(temperatures), 2)

    snapshot = {
        "average_temperature": average_temperature,
        "unit": config.get("TEMPERATURE_UNIT", "°C"),
        "status": temperature_status(average_temperature),
        "active_sensors_calculated": len(temperatures),
        "measurements_considered": measurement_count,
        "time_window_checked": "Past 1 hour",
        "latest_observation_at": newest_observation,
        "fetched_at": end_time.isoformat(),
        "bbox": [round(value, 6) for value in bbox],
        "phenomena_requested": phenomena,
        "source": "openSenseMap",
    }
    if region:
        snapshot["region"] = region

    cache_snapshot(snapshot)
    return snapshot


def get_temperature_snapshot():
    """Fetch a snapshot for the statically configured bounding box."""
    raw_bbox = config.get("TEMPERATURE_BBOX", "5.5,47.2,15.2,55.1")
    try:
        bbox = tuple(float(value.strip()) for value in raw_bbox.split(","))
    except ValueError as exc:
        raise ValueError("TEMPERATURE_BBOX must contain four numbers") from exc
    if len(bbox) != 4:
        raise ValueError("TEMPERATURE_BBOX must contain four numbers")
    return fetch_temperature_snapshot(bbox)


def check_sensebox_accessible(box_id):
    """Return whether one configured senseBox API resource is accessible."""
    data_url = config.get(
        "TEMPERATURE_API_URL",
        "https://api.opensensemap.org/boxes/data",
    )
    api_base_url = data_url.split("/boxes/data", maxsplit=1)[0].rstrip("/")
    try:
        timeout = min(
            3.0,
            max(0.5, float(config.get("READYZ_REQUEST_TIMEOUT", "2"))),
        )
    except ValueError:
        timeout = 2.0

    try:
        response = requests.get(
            f"{api_base_url}/boxes/{box_id}",
            timeout=timeout,
        )
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException:
        return False


def count_inaccessible_senseboxes(sensebox_ids):
    """Check configured senseBoxes concurrently and count failures."""
    if not sensebox_ids:
        return 0
    workers = min(len(sensebox_ids), 5)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = executor.map(check_sensebox_accessible, sensebox_ids)
        return sum(1 for accessible in results if not accessible)


def validate_region_parameters():
    """Parse and validate public region-temperature query parameters."""
    try:
        latitude = float(request.args["lat"])
        longitude = float(request.args["lon"])
        radius_km = float(request.args.get("radius_km", "10"))
    except KeyError as exc:
        raise ValueError(f"Missing query parameter: {exc.args[0]}") from exc
    except ValueError as exc:
        raise ValueError("lat, lon, and radius_km must be numbers") from exc

    if not -90 <= latitude <= 90:
        raise ValueError("lat must be between -90 and 90")
    if not -180 <= longitude <= 180:
        raise ValueError("lon must be between -180 and 180")
    if not 1 <= radius_km <= 50:
        raise ValueError("radius_km must be between 1 and 50")

    region_name = request.args.get("name", "Selected region").strip()[:120]
    selected_bbox = None
    raw_bbox = request.args.get("bbox", "").strip()
    if raw_bbox:
        try:
            selected_bbox = tuple(
                float(value.strip()) for value in raw_bbox.split(",")
            )
        except ValueError as exc:
            raise ValueError("bbox must contain four numbers") from exc
        if len(selected_bbox) != 4:
            raise ValueError("bbox must contain four numbers")
        west, south, east, north = selected_bbox
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError("bbox coordinates are invalid")
        if east - west > 24 or north - south > 18:
            raise ValueError("bbox is too large")

    return (
        latitude,
        longitude,
        radius_km,
        region_name or "Selected region",
        selected_bbox,
    )


def normalize_region_bbox(raw_bbox, latitude, longitude):
    """Convert a Nominatim bbox and cap it to a safe regional area."""
    if not isinstance(raw_bbox, list) or len(raw_bbox) != 4:
        return None
    try:
        south, north, west, east = (float(value) for value in raw_bbox)
    except (TypeError, ValueError):
        return None
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        return None

    half_width = 12.0
    half_height = 9.0
    bounded = (
        max(west, longitude - half_width),
        max(south, latitude - half_height),
        min(east, longitude + half_width),
        min(north, latitude + half_height),
    )
    return [round(value, 6) for value in bounded]


def acquire_nominatim_slot():
    """Enforce at most one uncached Nominatim request per second."""
    try:
        return bool(
            cache.set(
                "hivebox:nominatim:request-slot",
                "1",
                nx=True,
                ex=1,
            )
        )
    except RedisError:
        global _last_nominatim_request
        with _nominatim_lock:
            now = time.monotonic()
            if now - _last_nominatim_request < 1:
                return False
            _last_nominatim_request = now
            return True


def api_error(message, status_code, code):
    """Return a consistent API error body."""
    return jsonify({"error": {"code": code, "message": message}}), status_code


@app.before_request
def apply_public_api_rate_limit():
    """Apply a Valkey-backed fixed-window limit to public API routes."""
    if not request.path.startswith("/api/"):
        return None

    try:
        limit = max(1, int(config.get("API_RATE_LIMIT_PER_MINUTE", "60")))
    except ValueError:
        limit = 60

    client_address = request.remote_addr or "unknown"
    minute = int(time.time() // 60)
    digest = hashlib.sha256(client_address.encode("utf-8")).hexdigest()[:16]
    key = f"hivebox:rate:{minute}:{digest}"

    try:
        with cache.pipeline(transaction=True) as pipeline:
            pipeline.incr(key)
            pipeline.expire(key, 90)
            count, _ = pipeline.execute()
    except RedisError:
        return None

    if count > limit:
        return api_error("Too many requests; try again shortly", 429, "rate_limited")
    return None


@app.route("/", methods=["GET"])
def index():
    """Render the public HiveBox explorer."""
    return render_template("index.html", version=__version__)


@app.route("/healthz", methods=["GET"])
def health_check():
    """Report basic process liveness without calling dependencies."""
    return jsonify({"status": "alive", "version": __version__}), 200


@app.route("/readyz", methods=["GET"])
def readiness_check():
    """Report readiness from configured senseBoxes and cached-data age."""
    sensebox_ids = get_configured_sensebox_ids()
    if not sensebox_ids:
        return jsonify(
            {
                "status": "not ready",
                "reason": "TEMPERATURE_SENSEBOX_IDS is not configured",
                "configured_senseboxes": 0,
            }
        ), 503

    inaccessible_count = count_inaccessible_senseboxes(sensebox_ids)
    majority_threshold = (len(sensebox_ids) // 2) + 1
    majority_inaccessible = inaccessible_count >= majority_threshold
    cache_age_seconds = get_cached_snapshot_age_seconds()
    cache_is_stale = cache_age_seconds is None or cache_age_seconds > 300
    is_ready = not (majority_inaccessible and cache_is_stale)

    return jsonify(
        {
            "status": "ready" if is_ready else "not ready",
            "configured_senseboxes": len(sensebox_ids),
            "inaccessible_senseboxes": inaccessible_count,
            "majority_threshold": majority_threshold,
            "cache_age_seconds": (
                round(cache_age_seconds, 2)
                if cache_age_seconds is not None
                else None
            ),
            "cache_is_stale": cache_is_stale,
        }
    ), 200 if is_ready else 503


@app.route("/metrics", methods=["GET"])
def get_prometheus_metrics():
    """Return Prometheus metrics."""
    metric_fetch_counter.inc()
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


@app.route("/version", methods=["GET"])
def print_version():
    """Return the current application version."""
    version_fetch_counter.inc()
    return __version__


@app.route("/temperature", methods=["GET"])
def get_average_temperature():
    """Return temperature for the statically configured bounding box."""
    temperature_fetch_counter.labels("configured").inc()
    with temperature_fetch_duration.labels("configured").time():
        try:
            return jsonify(get_temperature_snapshot()), 200
        except requests.exceptions.RequestException:
            upstream_error_counter.labels("opensensemap").inc()
            return api_error(
                "Failed to connect to openSenseMap",
                502,
                "opensensemap_unavailable",
            )
        except ValueError as exc:
            return api_error(str(exc), 503, "temperature_unavailable")


@app.route("/api/regions/search", methods=["GET"])
def search_regions():
    """Resolve an explicit place search through Nominatim."""
    query = request.args.get("q", "").strip()
    if not 2 <= len(query) <= 120:
        return api_error(
            "q must contain between 2 and 120 characters",
            400,
            "invalid_query",
        )

    cache_key = (
        "hivebox:region-search:v2:"
        f"{hashlib.sha256(query.casefold().encode()).hexdigest()}"
    )
    cached_results = cache_get_json(cache_key)
    if cached_results is not None:
        return jsonify({"query": query, "results": cached_results, "cached": True})

    if not acquire_nominatim_slot():
        return api_error(
            "Location search is limited to one uncached request per second",
            429,
            "geocoder_rate_limited",
        )

    headers = {
        "User-Agent": config.get(
            "NOMINATIM_USER_AGENT",
            "HiveBox/0.0.1 (https://github.com/DevOpsHiveHQ/hivebox)",
        )
    }
    params = {
        "q": query,
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": 5,
        "layer": "address",
    }
    try:
        response = requests.get(
            config.get(
                "NOMINATIM_API_URL",
                "https://nominatim.openstreetmap.org/search",
            ),
            params=params,
            headers=headers,
            timeout=min(get_request_timeout(), 10),
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.exceptions.RequestException, ValueError):
        upstream_error_counter.labels("nominatim").inc()
        return api_error(
            "Location search is temporarily unavailable",
            502,
            "geocoder_unavailable",
        )

    results = []
    for item in payload[:5] if isinstance(payload, list) else []:
        try:
            latitude = float(item["lat"])
            longitude = float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        address = item.get("address") or {}
        place_type = str(item.get("addresstype") or item.get("type", "place"))
        result = {
            "display_name": str(item.get("display_name", query)),
            "lat": latitude,
            "lon": longitude,
            "type": place_type,
            "country_code": str(address.get("country_code", "")).upper(),
        }
        if place_type in {"country", "state", "province", "region"}:
            region_bbox = normalize_region_bbox(
                item.get("boundingbox"),
                latitude,
                longitude,
            )
            if region_bbox:
                result["bbox"] = region_bbox
        results.append(result)

    cache_set_json(cache_key, results, ttl_seconds=86400)
    return jsonify({"query": query, "results": results, "cached": False})


@app.route("/api/temperature", methods=["GET"])
def get_region_temperature():
    """Return temperature near a validated latitude and longitude."""
    try:
        (
            latitude,
            longitude,
            radius_km,
            region_name,
            selected_bbox,
        ) = validate_region_parameters()
    except ValueError as exc:
        return api_error(str(exc), 400, "invalid_region")

    location_key = (
        ":".join(f"{value:.4f}" for value in selected_bbox)
        if selected_bbox
        else f"{latitude:.4f}:{longitude:.4f}:{radius_km:.1f}"
    )
    cache_key = f"hivebox:region-temperature:{location_key}"
    cached_snapshot = cache_get_json(cache_key)
    if cached_snapshot is not None:
        cached_snapshot["cached"] = True
        return jsonify(cached_snapshot)

    bbox = selected_bbox or calculate_bbox(latitude, longitude, radius_km)
    temperature_fetch_counter.labels("region").inc()
    with temperature_fetch_duration.labels("region").time():
        try:
            snapshot = fetch_temperature_snapshot(
                bbox,
                region={
                    "name": region_name,
                    "lat": latitude,
                    "lon": longitude,
                    "radius_km": radius_km,
                    "area_mode": selected_bbox is not None,
                },
            )
        except requests.exceptions.RequestException:
            upstream_error_counter.labels("opensensemap").inc()
            return api_error(
                "openSenseMap is temporarily unavailable",
                502,
                "opensensemap_unavailable",
            )
        except ValueError as exc:
            return api_error(str(exc), 404, "no_temperature_data")

    snapshot["cached"] = False
    cache_set_json(cache_key, snapshot, ttl_seconds=300)
    return jsonify(snapshot)


def upload_snapshot_to_minio(snapshot):
    """Upload a uniquely named temperature snapshot to MinIO/S3."""
    secure = config.get("MINIO_SECURE", "false").lower() in {"1", "true", "yes"}
    client = Minio(
        config.get("MINIO_ENDPOINT", "localhost:9000"),
        access_key=config.get("MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=config.get("MINIO_SECRET_KEY", "minioadmin"),
        secure=secure,
    )
    bucket = config.get("MINIO_BUCKET", "hivebox")
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)

    now = datetime.now(timezone.utc)
    object_name = (
        "temperature/"
        f"{now.strftime('%Y/%m/%d/%H-%M-%S-%f')}-{uuid4().hex[:8]}.json"
    )
    data = json.dumps(snapshot).encode("utf-8")
    client.put_object(
        bucket,
        object_name,
        io.BytesIO(data),
        len(data),
        content_type="application/json",
    )
    return object_name


def store_current_snapshot(trigger):
    """Fetch and store the configured-region snapshot."""
    snapshot = get_temperature_snapshot()
    snapshot["stored_at"] = datetime.now(timezone.utc).isoformat()
    object_name = upload_snapshot_to_minio(snapshot)
    store_counter.labels(trigger, "success").inc()
    return snapshot, object_name


@app.route("/store", methods=["POST"])
def store_data():
    """Trigger an authenticated snapshot storage operation when configured."""
    expected_key = config.get("STORE_API_KEY", "")
    supplied_key = request.headers.get("X-API-Key", "")
    if expected_key and not hmac.compare_digest(expected_key, supplied_key):
        return api_error("A valid X-API-Key is required", 401, "unauthorized")

    try:
        snapshot, object_name = store_current_snapshot("manual")
    except Exception as exc:  # normalize storage SDK and transport failures
        store_counter.labels("manual", "failure").inc()
        logger.exception("Manual snapshot storage failed: %s", exc)
        return api_error("Snapshot storage failed", 502, "storage_failed")

    return jsonify(
        {
            "message": "Snapshot stored successfully",
            "object_name": object_name,
            "data": snapshot,
        }
    ), 200


def periodic_store():
    """Run snapshot storage in a dedicated worker process."""
    try:
        interval_seconds = max(60, int(config.get("STORE_INTERVAL_SECONDS", "300")))
    except ValueError:
        interval_seconds = 300

    logger.info("HiveBox storage worker started; interval=%ss", interval_seconds)
    while True:
        try:
            _, object_name = store_current_snapshot("periodic")
            logger.info("Periodic snapshot stored as %s", object_name)
        except Exception as exc:  # worker must survive dependency outages
            store_counter.labels("periodic", "failure").inc()
            logger.exception("Periodic snapshot storage failed: %s", exc)
        time.sleep(interval_seconds)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        periodic_store()
    else:
        app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
