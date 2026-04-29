"""Shared pytest fixtures.

The app uses a CSV-on-disk store rooted at the constant ``DATA_DIR`` defined
in ``app.py``.  We monkey-patch that to a per-test tmp dir so tests are
hermetic and can run in parallel without trampling real poll data.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# Make the voting-app package importable regardless of where pytest is run.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def app_module(tmp_path, monkeypatch):
    """Import app.py with DATA_DIR redirected to a tmp_path.

    Importing ``app`` has side effects (it chdirs and creates DATA_DIR), so we
    reload it fresh for each test inside an isolated working directory.
    """
    # Move into the tmp dir BEFORE import so the chdir() inside app.py (which
    # cd's to the file's directory) doesn't matter — we then point DATA_DIR at
    # an absolute path under tmp.
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Force re-import so module-level state (DATA_DIR, secret key, os.chdir)
    # is reset every test.
    if "app" in sys.modules:
        del sys.modules["app"]
    if "algorithms" in sys.modules:
        del sys.modules["algorithms"]

    import app as app_mod  # noqa: WPS433  -- runtime import is intentional

    # Override DATA_DIR to our tmp; also chdir there so relative paths in
    # read_csv / write_csv land under tmp_path.
    monkeypatch.setattr(app_mod, "DATA_DIR", str(data_dir))
    monkeypatch.chdir(tmp_path)

    # The module-level `seed_first_admin()` already ran during import using
    # the *real* data directory. Re-seed inside the test's tmp dir so the
    # admin user actually exists where the test expects it.
    app_mod.seed_first_admin()

    app_mod.app.config.update(TESTING=True)
    return app_mod


@pytest.fixture
def client(app_module):
    """Flask test client with a fresh app + tmp data dir."""
    return app_module.app.test_client()


@pytest.fixture
def admin_client(client, app_module):
    """A test client that is already logged in as admin."""
    resp = client.post(
        "/admin",
        data={"username": app_module.ADMIN_USER, "password": app_module.ADMIN_PASS},
        follow_redirects=False,
    )
    assert resp.status_code == 302, "admin login should redirect on success"
    return client


@pytest.fixture
def sample_poll(admin_client, app_module):
    """Create a poll with three options via the admin route, return its id."""
    resp = admin_client.post(
        "/admin/create",
        data={
            "title": "Lunch",
            "description": "Where to eat",
            "max_score": "5",
            "options": ["Pizza", "Sushi", "Tacos"],
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    # /admin/create redirects to /admin/poll/<poll_id>
    poll_id = resp.headers["Location"].rsplit("/", 1)[-1]
    return poll_id
