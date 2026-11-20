"""Test fixtures: isolated temp data dir + SQLite DB per session, real model loaded once."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_TMP = Path(tempfile.mkdtemp(prefix="pd-test-"))
os.environ.update({
    "PD_ENV": "test", "PD_DATA_DIR": str(_TMP), "PD_DB_URL": os.environ.get("PD_TEST_DB_URL") or f"sqlite:///{_TMP / 'test.db'}",
    "PD_UPLOAD_DIR": str(_TMP / "uploads"), "PD_LLM": "0", "PD_EMAIL_BACKEND": "console",
    "PD_ADMIN_EMAILS": "admin@example.com", "PD_REQUIRE_VERIFIED_EMAIL": "0", "PD_GUEST_SCANS_PER_DAY": "50",
    "PD_LOAD_MODELS": os.environ.get("PD_LOAD_MODELS", "1"), "PD_DEVICE": os.environ.get("PD_DEVICE", "cpu"),
})
# Extra data the seed step reads (dataset metadata) must not come from the real data dir.
(_TMP / "extra" / "_sources").mkdir(parents=True)

from fastapi.testclient import TestClient  # noqa: E402

from app.core import ratelimit  # noqa: E402
from app.server import app  # noqa: E402

SAMPLES = ROOT / "app" / "static" / "samples"


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture(autouse=True)
def _reset_limits():
    ratelimit.reset()
    yield


def _csrf(c):
    return {"X-CSRF-Token": c.cookies.get("pd_csrf", "")}


def register(email, password="correct-horse-42", name="Test Farmer"):
    """Return a *new* TestClient logged in as a fresh user (separate cookie jar)."""
    c = TestClient(app)
    r = c.post("/api/v1/auth/register", json={"email": email, "name": name, "password": password})
    assert r.status_code == 201, r.text
    c.headers.update(_csrf(c))
    return c


@pytest.fixture
def user_client(client, request):
    return register(f"user-{request.node.name[:40]}@example.com".lower())


def sample(name="tomato-early-blight.jpg"):
    return (SAMPLES / name).read_bytes()
