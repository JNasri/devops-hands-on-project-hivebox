"""Unit tests for the HiveBox Flask application."""

import json
import sys
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main  # noqa: E402


class FakePipeline:
    """Small in-memory implementation of the Redis pipeline calls we use."""

    def __init__(self, backend):
        self.backend = backend
        self.operations = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def set(self, key, value, **kwargs):
        self.operations.append(("set", key, value, kwargs))
        return self

    def incr(self, key):
        self.operations.append(("incr", key, None, {}))
        return self

    def expire(self, key, seconds):
        self.operations.append(("expire", key, seconds, {}))
        return self

    def execute(self):
        results = []
        for operation, key, value, options in self.operations:
            if operation == "set":
                results.append(self.backend.set(key, value, **options))
            elif operation == "incr":
                count = int(self.backend.values.get(key, "0")) + 1
                self.backend.values[key] = str(count)
                results.append(count)
            elif operation == "expire":
                results.append(True)
        return results


class FakeCache:
    """In-memory Valkey substitute for unit tests."""

    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, nx=False, **_kwargs):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def pipeline(self, **_kwargs):
        return FakePipeline(self)


class FakeResponse:
    """Configurable requests response substitute."""

    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(str(self.status_code))


@pytest.fixture(autouse=True)
def fake_cache(monkeypatch):
    """Prevent every test from connecting to a real Valkey instance."""
    test_cache = FakeCache()
    monkeypatch.setattr(main, "cache", test_cache)
    monkeypatch.setitem(main.config, "STORE_API_KEY", "")
    return test_cache


@pytest.fixture
def client():
    """Return a Flask test client."""
    main.app.config.update(TESTING=True)
    return main.app.test_client()


def test_homepage_renders_explorer(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"Field Temperature Explorer" in response.data
    assert b"region-form" in response.data
    assert b"reading-loader" in response.data
    assert b'aria-busy="false"' in response.data


def test_version_and_health_endpoints(client):
    version_response = client.get("/version")
    health_response = client.get("/healthz")

    assert version_response.status_code == 200
    assert version_response.data.decode() == main.__version__
    assert health_response.get_json() == {
        "status": "alive",
        "version": main.__version__,
    }


def test_temperature_status_boundaries():
    assert main.temperature_status(9.9) == "Too Cold"
    assert main.temperature_status(10) == "Good"
    assert main.temperature_status(36) == "Good"
    assert main.temperature_status(37) == "Too Hot"


def test_parse_temperature_uses_latest_value_per_sensor():
    measurements = [
        {"sensorId": "a", "value": "10", "createdAt": "2026-07-31T10:00:00Z"},
        {"sensorId": "a", "value": "20", "createdAt": "2026-07-31T10:05:00Z"},
        {"sensorId": "b", "value": "30", "createdAt": "2026-07-31T10:02:00Z"},
        {"sensorId": "bad", "value": "not-a-number"},
    ]

    temperatures, measurement_count, newest = main.parse_temperature_measurements(
        measurements
    )

    assert sorted(temperatures) == [20.0, 30.0]
    assert measurement_count == 3
    assert newest == "2026-07-31T10:05:00Z"


def test_temperature_phenomena_include_global_labels(monkeypatch):
    monkeypatch.delitem(main.config, "TEMPERATURE_PHENOMENA", raising=False)
    monkeypatch.setitem(main.config, "TEMPERATURE_PHENOMENON", "Temperatur")

    phenomena = main.get_temperature_phenomena()

    assert phenomena == [
        "Temperatur",
        "Temperature",
        "Temperatura",
        "Température",
        "Lufttemperatur",
    ]


def test_fetch_temperature_combines_phenomenon_labels(monkeypatch):
    payloads = {
        "Temperatur": [
            {"sensorId": "german", "value": "20", "createdAt": "2026-07-31T10:00:00Z"}
        ],
        "Temperature": [
            {"sensorId": "english", "value": "30", "createdAt": "2026-07-31T10:01:00Z"}
        ],
    }

    def fake_get(_url, params, timeout):
        assert timeout > 0
        return FakeResponse(payloads[params["phenomenon"]])

    monkeypatch.setattr(main, "get_temperature_phenomena", lambda: list(payloads))
    monkeypatch.setattr(main.requests, "get", fake_get)

    snapshot = main.fetch_temperature_snapshot((13.0, 52.0, 14.0, 53.0))

    assert snapshot["average_temperature"] == 25.0
    assert snapshot["active_sensors_calculated"] == 2
    assert snapshot["phenomena_requested"] == ["Temperatur", "Temperature"]


def test_fetch_temperature_snapshot(monkeypatch, fake_cache):
    payload = [
        {"sensorId": "a", "value": "20", "createdAt": "2026-07-31T10:00:00Z"},
        {"sensorId": "b", "value": "30", "createdAt": "2026-07-31T10:01:00Z"},
    ]
    monkeypatch.setattr(main.requests, "get", lambda *args, **kwargs: FakeResponse(payload))

    snapshot = main.fetch_temperature_snapshot((13.0, 52.0, 14.0, 53.0))

    assert snapshot["average_temperature"] == 25.0
    assert snapshot["active_sensors_calculated"] == 2
    assert snapshot["status"] == "Good"
    assert fake_cache.get("hivebox:latest_snapshot") is not None


def test_configured_temperature_endpoint_handles_upstream_failure(client, monkeypatch):
    def fail():
        raise requests.exceptions.Timeout()

    monkeypatch.setattr(main, "get_temperature_snapshot", fail)
    response = client.get("/temperature")

    assert response.status_code == 502
    assert response.get_json()["error"]["code"] == "opensensemap_unavailable"


def test_region_search_returns_normalized_results(client, monkeypatch):
    payload = [
        {
            "display_name": "Berlin, Germany",
            "lat": "52.517",
            "lon": "13.388",
            "type": "city",
            "addresstype": "city",
            "address": {"country_code": "de"},
        }
    ]

    def fake_get(url, params, headers, timeout):
        assert params["q"] == "Berlin"
        assert params["format"] == "jsonv2"
        assert "HiveBox" in headers["User-Agent"]
        return FakeResponse(payload)

    monkeypatch.setattr(main.requests, "get", fake_get)
    response = client.get("/api/regions/search?q=Berlin")

    assert response.status_code == 200
    body = response.get_json()
    assert body["cached"] is False
    assert body["results"][0]["country_code"] == "DE"
    assert body["results"][0]["lat"] == 52.517


def test_country_search_returns_bounded_area(client, monkeypatch):
    payload = [
        {
            "display_name": "France",
            "lat": "46.603354",
            "lon": "1.888334",
            "type": "administrative",
            "addresstype": "country",
            "boundingbox": ["-50.2", "51.3", "-178.3", "172.3"],
            "address": {"country_code": "fr"},
        }
    ]
    monkeypatch.setattr(
        main.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(payload),
    )

    response = client.get("/api/regions/search?q=France")

    result = response.get_json()["results"][0]
    assert result["type"] == "country"
    assert len(result["bbox"]) == 4
    assert result["bbox"][2] - result["bbox"][0] <= 24
    assert result["bbox"][3] - result["bbox"][1] <= 18


def test_region_search_rejects_short_query(client):
    response = client.get("/api/regions/search?q=B")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_query"


def test_region_temperature_returns_fresh_snapshot(client, monkeypatch):
    snapshot = {
        "average_temperature": 18.5,
        "unit": "°C",
        "status": "Good",
        "active_sensors_calculated": 4,
        "measurements_considered": 12,
        "source": "openSenseMap",
    }
    monkeypatch.setattr(
        main,
        "fetch_temperature_snapshot",
        lambda bbox, region=None: {**snapshot, "bbox": list(bbox), "region": region},
    )

    response = client.get(
        "/api/temperature?lat=52.52&lon=13.40&radius_km=10&name=Berlin"
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["cached"] is False
    assert body["region"]["name"] == "Berlin"
    assert body["region"]["radius_km"] == 10.0
    assert body["region"]["area_mode"] is False


def test_region_temperature_accepts_bounded_area(client, monkeypatch):
    captured = {}

    def fake_fetch(bbox, region=None):
        captured["bbox"] = bbox
        return {
            "average_temperature": 21.0,
            "unit": "°C",
            "status": "Good",
            "active_sensors_calculated": 2,
            "measurements_considered": 2,
            "source": "openSenseMap",
            "region": region,
        }

    monkeypatch.setattr(main, "fetch_temperature_snapshot", fake_fetch)
    response = client.get(
        "/api/temperature?lat=46.6&lon=1.9&radius_km=10&name=France"
        "&bbox=-6.1,40.6,9.9,52.6"
    )

    assert response.status_code == 200
    assert captured["bbox"] == (-6.1, 40.6, 9.9, 52.6)
    assert response.get_json()["region"]["area_mode"] is True


def test_region_temperature_rejects_unsafe_radius(client):
    response = client.get("/api/temperature?lat=52&lon=13&radius_km=500")

    assert response.status_code == 400
    assert "between 1 and 50" in response.get_json()["error"]["message"]


@pytest.mark.parametrize(
    ("inaccessible", "cache_age", "expected_status"),
    [
        (0, 20, 200),
        (2, 20, 200),
        (0, 400, 200),
        (2, 400, 503),
        (2, None, 503),
    ],
)
def test_readiness_truth_table(
    client,
    monkeypatch,
    inaccessible,
    cache_age,
    expected_status,
):
    monkeypatch.setattr(main, "get_configured_sensebox_ids", lambda: ["a", "b", "c"])
    monkeypatch.setattr(
        main,
        "count_inaccessible_senseboxes",
        lambda _ids: inaccessible,
    )
    monkeypatch.setattr(main, "get_cached_snapshot_age_seconds", lambda: cache_age)

    response = client.get("/readyz")

    assert response.status_code == expected_status


def test_readiness_rejects_missing_box_configuration(client, monkeypatch):
    monkeypatch.setattr(main, "get_configured_sensebox_ids", lambda: [])

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.get_json()["configured_senseboxes"] == 0


def test_store_endpoint_uploads_snapshot(client, monkeypatch):
    snapshot = {"average_temperature": 25.0, "status": "Good"}
    monkeypatch.setattr(
        main,
        "store_current_snapshot",
        lambda _trigger: (snapshot, "temperature/example.json"),
    )

    response = client.post("/store")

    assert response.status_code == 200
    assert response.get_json()["object_name"] == "temperature/example.json"


def test_store_endpoint_requires_key_when_configured(client, monkeypatch):
    monkeypatch.setitem(main.config, "STORE_API_KEY", "secret")

    response = client.post("/store", headers={"X-API-Key": "wrong"})

    assert response.status_code == 401


def test_store_endpoint_normalizes_dependency_failure(client, monkeypatch):
    def fail(_trigger):
        raise RuntimeError("storage is unavailable")

    monkeypatch.setattr(main, "store_current_snapshot", fail)

    response = client.post("/store")

    assert response.status_code == 502
    assert response.get_json()["error"]["code"] == "storage_failed"


def test_metrics_endpoint(client):
    response = client.get("/metrics")

    assert response.status_code == 200
    assert b"hivebox_metrics_requests_total" in response.data


def test_cache_snapshot_writes_both_keys(fake_cache):
    assert main.cache_snapshot({"temperature": 21}) is True
    assert json.loads(fake_cache.get("hivebox:latest_snapshot")) == {"temperature": 21}
    assert fake_cache.get("hivebox:latest_snapshot_ts") is not None


def test_cache_snapshot_failure_is_nonfatal(monkeypatch):
    class BrokenCache:
        def pipeline(self, **_kwargs):
            raise main.RedisError("Valkey unavailable")

    monkeypatch.setattr(main, "cache", BrokenCache())

    assert main.cache_snapshot({"temperature": 21}) is False
