'''Test the Flask application endpoints.'''

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main  # noqa: E402


def test_version_endpoint_returns_current_version():
    '''Test that the /version endpoint returns the current app version.'''
    client = main.app.test_client()
    response = client.get('/version')

    assert response.status_code == 200
    assert response.data.decode('utf-8') == main.__version__


def test_get_temperature_snapshot_returns_real_values(monkeypatch):
    '''Test that the helper returns a calculated temperature snapshot.'''

    class FakeResponse:
        '''A fake response object to simulate requests.get() behavior.'''

        def __init__(self, payload):
            self._payload = payload
            self.headers = {"Content-Type": "application/json"}

        def raise_for_status(self):
            '''Simulate raise_for_status() method.'''
            return None

        def json(self):
            '''Simulate json() method to return the payload.'''
            return self._payload

    def fake_get(url, params=None, timeout=None):
        '''A fake requests.get() function that returns a FakeResponse.'''
        return FakeResponse(
            [
                {"value": 20},
                {"value": 30},
            ]
        )

    monkeypatch.setattr(main.requests, "get", fake_get)

    snapshot = main.get_temperature_snapshot()

    assert snapshot["status"] == "Good"
    assert snapshot["average_temperature"] == 25.0
    assert snapshot["active_sensors_calculated"] == 2


def test_temperature_endpoint_returns_expected_structure(monkeypatch):
    '''Test that the /temperature endpoint returns the expected JSON.'''

    class FakeResponse:
        '''A fake response object to simulate requests.get() behavior.'''

        def __init__(self, payload):
            self._payload = payload
            self.headers = {"Content-Type": "application/json"}

        def raise_for_status(self):
            '''Simulate raise_for_status() method.'''
            return None

        def json(self):
            '''Simulate json() method to return the payload.'''
            return self._payload

    def fake_get(url, params=None, timeout=None):
        '''A fake requests.get() function that returns a FakeResponse.'''
        return FakeResponse(
            [
                {"value": 20},
                {"value": 30},
            ]
        )

    monkeypatch.setattr(main.requests, "get", fake_get)

    client = main.app.test_client()
    response = client.get("/temperature")

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "Good"
    assert data["average_temperature"] == 25.0


def test_upload_snapshot_to_minio_calls_client(monkeypatch):
    '''Test that the MinIO helper creates a bucket and uploads an object.'''

    class FakeMinioClient:
        '''A fake MinIO client for testing.'''

        def __init__(self):
            self.bucket_exists_called = False
            self.make_bucket_called = False
            self.put_object_called = False

        def bucket_exists(self, bucket_name):
            self.bucket_exists_called = True
            return False

        def make_bucket(self, bucket_name):
            self.make_bucket_called = True

        def put_object(self, bucket_name, object_name, data, length):
            self.put_object_called = True
            assert bucket_name == "hivebox"
            assert object_name.startswith("temperature/")
            assert length > 0

    fake_client = FakeMinioClient()

    monkeypatch.setattr(main, "Minio", lambda *args, **kwargs: fake_client)

    snapshot = {"average_temperature": 25.0, "status": "Good"}
    main.upload_snapshot_to_minio(snapshot)

    assert fake_client.bucket_exists_called is True
    assert fake_client.make_bucket_called is True
    assert fake_client.put_object_called is True


def test_metrics_endpoint_returns_metrics():
    '''Test that the /metrics endpoint returns metrics data.'''
    client = main.app.test_client()
    response = client.get("/metrics")

    assert response.status_code == 200
    assert b"metric_fetch_counter" in response.data
