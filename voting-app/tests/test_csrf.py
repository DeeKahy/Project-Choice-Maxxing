"""CSRF protection tests (#4).

The CSRF guard short-circuits when `app.config["TESTING"]` is true so the
rest of the suite can keep using bare POSTs. These tests flip TESTING off
to exercise the real-world behaviour.
"""
import re

import pytest


@pytest.fixture
def prod_client(app_module):
    """A test client with TESTING disabled, so the CSRF guard fires."""
    app_module.app.config.update(TESTING=False)
    return app_module.app.test_client()


def _extract_csrf_token(html):
    match = re.search(
        rb'name="csrf_token"\s+value="([^"]+)"', html
    )
    assert match, "CSRF token field missing from page"
    return match.group(1).decode()


def test_post_without_token_is_rejected(prod_client):
    resp = prod_client.post(
        "/admin", data={"username": "admin", "password": "admin"}
    )
    assert resp.status_code == 400


def test_post_with_wrong_token_is_rejected(prod_client):
    # First fetch the login page so we have a session, then POST with a
    # tampered token.
    page = prod_client.get("/admin")
    real_token = _extract_csrf_token(page.data)
    bad = "x" * len(real_token)
    resp = prod_client.post(
        "/admin",
        data={"username": "admin", "password": "admin", "csrf_token": bad},
    )
    assert resp.status_code == 400


def test_post_with_correct_token_is_accepted(prod_client, app_module):
    page = prod_client.get("/admin")
    token = _extract_csrf_token(page.data)
    resp = prod_client.post(
        "/admin",
        data={
            "username": app_module.ADMIN_USER,
            "password": app_module.ADMIN_PASS,
            "csrf_token": token,
        },
    )
    assert resp.status_code == 302


def test_get_requests_do_not_require_token(prod_client):
    resp = prod_client.get("/admin")
    assert resp.status_code == 200
    # And the rendered form contains a fresh token to use on submit.
    assert b'name="csrf_token"' in resp.data


def test_csrf_token_is_consistent_within_session(prod_client):
    """The same token should be reused across multiple GETs in one session
    so users with multiple tabs open don't get random rejections."""
    a = _extract_csrf_token(prod_client.get("/admin").data)
    b = _extract_csrf_token(prod_client.get("/admin").data)
    assert a == b
