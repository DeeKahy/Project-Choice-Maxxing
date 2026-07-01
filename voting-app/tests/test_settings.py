"""Tests for the new fixes:

- favicon route (#5)
- closed-poll results banner + redirect (#6)
- duplicate-username vote does not crash (#8)
- admin settings page + public-signup on/off switch (#11, #13)
"""
import pytest


# ---------- favicon (#5) ----------


def test_favicon_redirects_to_svg(client):
    resp = client.get("/favicon.ico")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/static/favicon.svg")


# ---------- closed poll -> results (#6) ----------


def _close_poll(admin_client, poll_id):
    resp = admin_client.post(f"/admin/poll/{poll_id}/toggle")
    assert resp.status_code == 302


def test_voting_a_closed_poll_redirects_to_results(admin_client, client, sample_poll):
    _close_poll(admin_client, sample_poll)
    resp = client.get(f"/vote/{sample_poll}")
    assert resp.status_code == 302
    assert f"/results/{sample_poll}" in resp.headers["Location"]


def test_closed_poll_results_show_closed_banner(admin_client, client, sample_poll):
    _close_poll(admin_client, sample_poll)
    resp = client.get(f"/results/{sample_poll}")
    assert resp.status_code == 200
    assert b"This poll is closed" in resp.data


def test_open_poll_results_have_no_closed_banner(client, sample_poll):
    resp = client.get(f"/results/{sample_poll}")
    assert resp.status_code == 200
    assert b"This poll is closed" not in resp.data


# ---------- duplicate username vote does not crash (#8) ----------


def _vote(client, poll_id, username, scores):
    data = {"username": username}
    for opt_id, score in scores.items():
        data[f"score_{opt_id}"] = str(score)
    return client.post(f"/vote/{poll_id}", data=data)


def test_duplicate_username_vote_does_not_crash(client, sample_poll):
    first = _vote(client, sample_poll, "dupe", {1: 5, 2: 3, 3: 0})
    assert first.status_code == 302  # first vote succeeds -> redirect to results

    second = _vote(client, sample_poll, "dupe", {1: 1, 2: 1, 3: 1})
    # Must be a clean, rendered page (not a 500 crash).
    assert second.status_code == 200
    assert b"already voted" in second.data


# ---------- admin settings + signup switch (#11, #13) ----------


def test_signup_enabled_by_default(client):
    resp = client.get("/signup")
    assert resp.status_code == 200


def test_settings_page_requires_admin(client):
    # Not logged in -> redirected to login.
    resp = client.get("/admin/settings")
    assert resp.status_code == 302
    assert "/admin" in resp.headers["Location"]


def test_admin_can_view_settings(admin_client):
    resp = admin_client.get("/admin/settings")
    assert resp.status_code == 200
    assert b"Allow public sign-up" in resp.data


def test_admin_can_disable_signup(admin_client, app_module):
    # Toggle off: unchecked checkbox is simply absent from the form body.
    resp = admin_client.post("/admin/settings", data={})
    assert resp.status_code == 200
    assert app_module.signup_enabled() is False


def test_disabled_signup_blocks_get(admin_client, client):
    admin_client.post("/admin/settings", data={})
    resp = client.get("/signup")
    assert resp.status_code == 403
    assert b"disabled" in resp.data


def test_disabled_signup_blocks_account_creation(admin_client, client, app_module):
    admin_client.post("/admin/settings", data={})
    resp = client.post(
        "/signup",
        data={
            "username": "shouldnotexist",
            "password": "passw0rd",
            "confirm_password": "passw0rd",
        },
    )
    assert resp.status_code == 403
    assert app_module.get_user("shouldnotexist") is None


def test_signup_link_hidden_on_login_when_disabled(admin_client, client):
    # Enabled: link present.
    login = client.get("/admin")
    assert b"Create an account" in login.data
    # Disable, then the link disappears.
    admin_client.post("/admin/settings", data={})
    login = client.get("/admin")
    assert b"Create an account" not in login.data


def test_signup_can_be_re_enabled(admin_client, app_module):
    admin_client.post("/admin/settings", data={})
    assert app_module.signup_enabled() is False
    admin_client.post("/admin/settings", data={"signup_enabled": "on"})
    assert app_module.signup_enabled() is True
