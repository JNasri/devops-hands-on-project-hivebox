import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main


def test_version_endpoint_returns_current_version():
    # create Flask's test client out of main
    client = main.app.test_client()
    # call the /version endpoint, store response
    response = client.get('/version')

    # test 1: does it return 200?
    assert response.status_code == 200
    # test 2: does it return the current version?
    assert response.data.decode('utf-8') == main.__version__
