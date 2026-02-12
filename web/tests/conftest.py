"""Shared fixtures for web tests."""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.request

import pytest

E2E_PORT = 8787
E2E_BASE_URL = f"http://localhost:{E2E_PORT}"


@pytest.fixture(scope="session")
def base_url():
    return E2E_BASE_URL


@pytest.fixture(scope="session")
def e2e_server():
    """Start uvicorn on a test port, wait for ready, tear down after session.

    Note: No --reload for test server (avoids Windows file watcher issues).
    """
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "web.server:app",
            "--host", "127.0.0.1",
            "--port", str(E2E_PORT),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Wait for server to be ready (search index loads on startup)
    for _ in range(90):
        try:
            urllib.request.urlopen(f"{E2E_BASE_URL}/api/categories", timeout=2)
            break
        except Exception:
            time.sleep(1)
    else:
        proc.kill()
        raise RuntimeError("E2E server did not start in time")

    yield proc

    proc.kill()
    proc.wait()
