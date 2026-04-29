"""Tests for poll CRUD via the admin routes."""


def test_create_poll_redirects_to_admin_poll(admin_client):
    resp = admin_client.post(
        "/admin/create",
        data={
            "title": "Test Poll",
            "description": "x",
            "max_score": "5",
            "options": ["A", "B", "C"],
        },
    )
    assert resp.status_code == 302
    assert "/admin/poll/" in resp.headers["Location"]


def test_create_poll_rejects_single_option(admin_client, app_module):
    resp = admin_client.post(
        "/admin/create",
        data={
            "title": "Sparse",
            "max_score": "5",
            "options": ["Only", "", "  "],
        },
    )
    assert resp.status_code == 200
    assert b"At least two" in resp.data
    assert app_module.get_polls() == []


def test_create_poll_rejects_blank_title(admin_client, app_module):
    resp = admin_client.post(
        "/admin/create",
        data={"title": "   ", "max_score": "5", "options": ["A", "B"]},
    )
    assert resp.status_code == 200
    assert b"title is required" in resp.data
    assert app_module.get_polls() == []


def test_create_poll_rejects_invalid_max_score(admin_client, app_module):
    resp = admin_client.post(
        "/admin/create",
        data={"title": "x", "max_score": "100", "options": ["A", "B"]},
    )
    assert resp.status_code == 200
    assert b"3, 5, or 10" in resp.data
    assert app_module.get_polls() == []


def test_create_poll_dedupes_options(admin_client, app_module):
    resp = admin_client.post(
        "/admin/create",
        data={
            "title": "Dup",
            "max_score": "5",
            "options": ["Same", "Same", "Other"],
        },
    )
    assert resp.status_code == 302
    poll_id = resp.headers["Location"].rsplit("/", 1)[-1]
    options = app_module.get_options(poll_id)
    names = [o["name"] for o in options]
    assert names == ["Same", "Other"]


def test_create_poll_strips_title_and_description(admin_client, app_module):
    resp = admin_client.post(
        "/admin/create",
        data={
            "title": "  Trimmed  ",
            "description": "  desc  ",
            "max_score": "5",
            "options": ["A", "B"],
        },
    )
    poll_id = resp.headers["Location"].rsplit("/", 1)[-1]
    poll = app_module.get_poll(poll_id)
    assert poll["title"] == "Trimmed"
    assert poll["description"] == "desc"


def test_create_poll_preserves_form_on_validation_error(admin_client):
    """When the server rejects the form it should re-render with the user's
    typed values intact so they don't lose their work."""
    resp = admin_client.post(
        "/admin/create",
        data={
            "title": "  ",  # invalid
            "description": "Where to eat",
            "max_score": "10",
            "options": ["Pizza", "Sushi"],
        },
    )
    assert resp.status_code == 200
    assert b"Where to eat" in resp.data
    assert b"Pizza" in resp.data
    assert b"Sushi" in resp.data


def test_unauthenticated_user_cannot_create_poll(client):
    resp = client.post(
        "/admin/create", data={"title": "x", "max_score": "5", "options": ["A", "B"]}
    )
    assert resp.status_code == 302
    assert "/admin" in resp.headers["Location"]


def test_unauthenticated_user_cannot_delete_poll(client, sample_poll):
    resp = client.post(f"/admin/poll/{sample_poll}/delete")
    assert resp.status_code == 302
    assert "/admin" in resp.headers["Location"]


def test_admin_poll_404_for_unknown_id(admin_client):
    resp = admin_client.get("/admin/poll/does-not-exist")
    assert resp.status_code == 404


def test_toggle_poll_flips_is_open(admin_client, sample_poll, app_module):
    poll = app_module.get_poll(sample_poll)
    assert poll["is_open"] == "true"
    admin_client.post(f"/admin/poll/{sample_poll}/toggle")
    poll = app_module.get_poll(sample_poll)
    assert poll["is_open"] == "false"


def test_delete_poll_removes_csv_files(admin_client, sample_poll, app_module):
    import os

    options_path = f"{app_module.DATA_DIR}/options_{sample_poll}.csv"
    assert os.path.exists(options_path)
    admin_client.post(f"/admin/poll/{sample_poll}/delete")
    assert not os.path.exists(options_path)
    assert app_module.get_poll(sample_poll) is None
