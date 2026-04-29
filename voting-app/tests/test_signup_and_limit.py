"""Tests for the public signup flow + per-user poll limit (#17)."""
import pytest


# ---------- /signup ----------


def test_signup_page_renders(client):
    resp = client.get("/signup")
    assert resp.status_code == 200
    assert b"Create Account" in resp.data


def test_signup_creates_non_admin_account_and_logs_in(client, app_module):
    resp = client.post(
        "/signup",
        data={
            "username": "newbie",
            "password": "passw0rd",
            "confirm_password": "passw0rd",
        },
    )
    assert resp.status_code == 302
    assert "/admin/dashboard" in resp.headers["Location"]

    user = app_module.get_user("newbie")
    assert user is not None
    assert user["is_admin"] == "false"
    # Password was hashed.
    assert user["password_hash"] != "passw0rd"

    # Following the redirect should land on the dashboard now that we're
    # authenticated.
    dash = client.get("/admin/dashboard")
    assert dash.status_code == 200


def test_signup_rejects_password_mismatch(client, app_module):
    resp = client.post(
        "/signup",
        data={"username": "x", "password": "abcd", "confirm_password": "WXYZ"},
    )
    assert resp.status_code == 200
    assert b"do not match" in resp.data
    assert app_module.get_user("x") is None


def test_signup_rejects_short_password(client, app_module):
    resp = client.post(
        "/signup",
        data={"username": "x", "password": "ab", "confirm_password": "ab"},
    )
    assert resp.status_code == 200
    assert app_module.get_user("x") is None


def test_signup_rejects_invalid_username(client, app_module):
    resp = client.post(
        "/signup",
        data={
            "username": "has spaces",
            "password": "abcd",
            "confirm_password": "abcd",
        },
    )
    assert resp.status_code == 200
    assert app_module.get_user("has spaces") is None


def test_signup_rejects_taken_username(client, app_module):
    app_module.add_user("taken", "p1", is_admin_flag=False)
    resp = client.post(
        "/signup",
        data={
            "username": "taken",
            "password": "newpw",
            "confirm_password": "newpw",
        },
    )
    assert resp.status_code == 200
    assert b"already taken" in resp.data


# ---------- ownership ----------


def _signup_and_login(client, username, password="passw0rd"):
    client.post(
        "/signup",
        data={
            "username": username,
            "password": password,
            "confirm_password": password,
        },
    )


def _create_poll_as(client, title="Test", options=("A", "B")):
    resp = client.post(
        "/admin/create",
        data={
            "title": title,
            "max_score": "5",
            "options": list(options),
        },
    )
    assert resp.status_code == 302, resp.data
    return resp.headers["Location"].rsplit("/", 1)[-1]


def test_new_poll_records_owner(client, app_module):
    _signup_and_login(client, "alice")
    poll_id = _create_poll_as(client, title="Alice's poll")
    poll = app_module.get_poll(poll_id)
    assert poll["owner"] == "alice"


def test_dashboard_shows_only_own_polls_for_non_admin(client, app_module):
    _signup_and_login(client, "alice")
    alice_poll = _create_poll_as(client, title="Alice poll")

    # Admin creates a poll under their own account.
    other = app_module.app.test_client()
    other.post(
        "/admin",
        data={"username": app_module.ADMIN_USER, "password": app_module.ADMIN_PASS},
    )
    other.post(
        "/admin/create",
        data={"title": "Admin poll", "max_score": "5", "options": ["X", "Y"]},
    )

    # Alice's dashboard contains her poll only.
    dash = client.get("/admin/dashboard")
    assert b"Alice poll" in dash.data
    assert b"Admin poll" not in dash.data


def test_admin_dashboard_shows_all_polls(client, app_module):
    _signup_and_login(client, "alice")
    _create_poll_as(client, title="Alice poll")
    client.get("/admin/logout")

    # Log in as the seeded admin.
    client.post(
        "/admin",
        data={"username": app_module.ADMIN_USER, "password": app_module.ADMIN_PASS},
    )
    dash = client.get("/admin/dashboard")
    assert b"Alice poll" in dash.data


def test_non_owner_cannot_view_other_users_poll(client, app_module):
    # Alice creates a poll
    alice = app_module.app.test_client()
    _signup_and_login(alice, "alice")
    poll_id = _create_poll_as(alice, title="Alice")

    # Bob signs up and tries to manage Alice's poll.
    bob = app_module.app.test_client()
    _signup_and_login(bob, "bob")

    resp = bob.get(f"/admin/poll/{poll_id}")
    assert resp.status_code == 404


def test_non_owner_cannot_delete_other_users_poll(client, app_module):
    alice = app_module.app.test_client()
    _signup_and_login(alice, "alice")
    poll_id = _create_poll_as(alice, title="Alice")

    bob = app_module.app.test_client()
    _signup_and_login(bob, "bob")
    resp = bob.post(f"/admin/poll/{poll_id}/delete")
    assert resp.status_code == 404
    assert app_module.get_poll(poll_id) is not None


def test_owner_can_manage_their_own_poll(client, app_module):
    _signup_and_login(client, "alice")
    poll_id = _create_poll_as(client, title="Mine")
    resp = client.get(f"/admin/poll/{poll_id}")
    assert resp.status_code == 200
    # Owner can toggle and delete.
    client.post(f"/admin/poll/{poll_id}/toggle")
    poll = app_module.get_poll(poll_id)
    assert poll["is_open"] == "false"
    client.post(f"/admin/poll/{poll_id}/delete")
    assert app_module.get_poll(poll_id) is None


def test_admin_can_manage_any_poll(client, app_module):
    user_client = app_module.app.test_client()
    _signup_and_login(user_client, "alice")
    poll_id = _create_poll_as(user_client, title="Alice")

    admin_client = app_module.app.test_client()
    admin_client.post(
        "/admin",
        data={"username": app_module.ADMIN_USER, "password": app_module.ADMIN_PASS},
    )
    resp = admin_client.get(f"/admin/poll/{poll_id}")
    assert resp.status_code == 200
    admin_client.post(f"/admin/poll/{poll_id}/delete")
    assert app_module.get_poll(poll_id) is None


# ---------- per-user poll limit ----------


def test_poll_limit_blocks_creation_when_full(client, app_module, monkeypatch):
    """Drop the limit to 3 for speed and confirm the 4th poll is rejected
    with the expected message + popup script."""
    monkeypatch.setattr(app_module, "MAX_POLLS_PER_USER", 3)

    _signup_and_login(client, "alice")
    for i in range(3):
        _create_poll_as(client, title=f"poll{i}")

    # 4th attempt is rejected.
    resp = client.post(
        "/admin/create",
        data={"title": "overflow", "max_score": "5", "options": ["A", "B"]},
    )
    assert resp.status_code == 200
    assert b"reached the 3-poll limit" in resp.data
    # The popup script the user asked for must be present.
    assert b"alert(" in resp.data
    # Poll did NOT get persisted.
    assert all(p["title"] != "overflow" for p in app_module.get_polls())


def test_poll_limit_get_renders_friendly_message(client, app_module, monkeypatch):
    """A user already at the cap who navigates to /admin/create gets the
    error and a disabled submit button instead of a usable form."""
    monkeypatch.setattr(app_module, "MAX_POLLS_PER_USER", 1)
    _signup_and_login(client, "alice")
    _create_poll_as(client, title="only one")

    resp = client.get("/admin/create")
    assert resp.status_code == 200
    assert b"limit" in resp.data.lower()
    assert b"disabled" in resp.data


def test_poll_limit_resets_after_delete(client, app_module, monkeypatch):
    """Deleting a poll frees up a slot."""
    monkeypatch.setattr(app_module, "MAX_POLLS_PER_USER", 2)
    _signup_and_login(client, "alice")
    p1 = _create_poll_as(client, title="a")
    _create_poll_as(client, title="b")

    blocked = client.post(
        "/admin/create",
        data={"title": "c", "max_score": "5", "options": ["A", "B"]},
    )
    assert blocked.status_code == 200
    assert b"limit" in blocked.data.lower()

    client.post(f"/admin/poll/{p1}/delete")
    after = client.post(
        "/admin/create",
        data={"title": "c", "max_score": "5", "options": ["A", "B"]},
    )
    assert after.status_code == 302


def test_admin_is_exempt_from_poll_limit(client, app_module, monkeypatch):
    monkeypatch.setattr(app_module, "MAX_POLLS_PER_USER", 1)
    client.post(
        "/admin",
        data={"username": app_module.ADMIN_USER, "password": app_module.ADMIN_PASS},
    )
    # Admin can create well past the limit.
    for i in range(5):
        resp = client.post(
            "/admin/create",
            data={"title": f"a{i}", "max_score": "5", "options": ["X", "Y"]},
        )
        assert resp.status_code == 302


def test_dashboard_displays_poll_count_for_non_admin(client, app_module, monkeypatch):
    monkeypatch.setattr(app_module, "MAX_POLLS_PER_USER", 5)
    _signup_and_login(client, "alice")
    _create_poll_as(client, title="one")
    resp = client.get("/admin/dashboard")
    assert resp.status_code == 200
    assert b"1 / 5" in resp.data or b"1/5" in resp.data
