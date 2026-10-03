"""Explicit disposable administrator credentials for authenticated read fixtures."""
import os
import time
import requests

_cached = {}


def test_admin_headers():
    if os.environ.get("TEST_SUITE_ISOLATED") != "1" or os.environ.get("REACT_APP_BACKEND_URL") != "http://web":
        raise RuntimeError("Authenticated read fixture requires the disposable Compose suite")
    now = time.monotonic()
    if now - _cached.get("at", -1000) >= 30:
        response = requests.post("http://web/api/auth/login", json={"email": os.environ["ADMIN_EMAIL"], "password": os.environ["ADMIN_PASSWORD"]}, timeout=15)
        assert response.status_code == 200, response.text
        _cached.update(token=response.json()["access_token"], at=now)
    return {"Authorization": f"Bearer {_cached['token']}"}

# Imported helper must not be collected as a test.
test_admin_headers.__test__ = False
