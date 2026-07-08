'''Test the Flask application endpoints.'''

import sys
from pathlib import Path

import main  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_version_endpoint_returns_current_version():
    '''Test that the /version endpoint returns the current app version.'''
    client = main.app.test_client()
    response = client.get('/version')

    assert response.status_code == 200
    assert response.data.decode('utf-8') == main.__version__


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


def test_metrics_endpoint_returns_metrics():
    '''Test that the /metrics endpoint returns metrics data.'''
    client = main.app.test_client()
    response = client.get("/metrics")

    assert response.status_code == 200
    assert b"metric_fetch_counter" in response.data
