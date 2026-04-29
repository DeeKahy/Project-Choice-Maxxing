"""Auth & basic routing tests."""


def test_home_redirects_to_admin_login(client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/admin" in resp.headers["Location"]


def test_admin_login_with_correct_credentials(client, app_module):
    resp = client.post(
        "/admin",
        data={"username": app_module.ADMIN_USER, "password": app_module.ADMIN_PASS},
    )
    assert resp.status_code == 302
    assert "/admin/dashboard" in resp.headers["Location"]


def test_admin_login_with_wrong_password(client, app_module):
    resp = client.post(
        "/admin", data={"username": app_module.ADMIN_USER, "password": "wrong"}
    )
    assert resp.status_code == 200
    assert b"Invalid credentials" in resp.data


def test_admin_login_with_unknown_user(client):
    resp = client.post(
        "/admin", data={"username": "ghost", "password": "ghost"}
    )
    assert resp.status_code == 200
    assert b"Invalid credentials" in resp.data


def test_dashboard_requires_login(client):
    resp = client.get("/admin/dashboard")
    assert resp.status_code == 302
    assert "/admin" in resp.headers["Location"]


def test_logout_clears_session(admin_client):
    # admin_client is logged in
    resp = admin_client.get("/admin/dashboard")
    assert resp.status_code == 200
    admin_client.get("/admin/logout")
    resp = admin_client.get("/admin/dashboard")
    assert resp.status_code == 302
