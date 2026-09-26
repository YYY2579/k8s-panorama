"""认证与权限的接口测试：登录、登出、角色拦截、用户管理。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from .conftest import TEST_PASSWORD


# ---------- 登录 / 登出 / me ----------


def test_login_wrong_password_401(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "nope"})
    assert r.status_code == 401


def test_login_unknown_user_401(client):
    r = client.post("/api/auth/login", json={"username": "ghost", "password": "x"})
    assert r.status_code == 401


def test_login_error_message_does_not_leak_user(client):
    """用户不存在与口令错误的提示必须一致，避免暴露用户名。"""
    a = client.post("/api/auth/login", json={"username": "ghost", "password": "x"}).json()["detail"]
    b = client.post("/api/auth/login", json={"username": "admin", "password": "x"}).json()["detail"]
    assert a == b


def test_login_success_returns_user(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": TEST_PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == "admin"
    assert body["role"] == "admin"
    assert "password" not in body and "password_hash" not in body


def test_me_requires_login(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_after_login(admin_client):
    r = admin_client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["username"] == "admin"


def test_logout_clears_session(admin_client):
    assert admin_client.post("/api/auth/logout").status_code == 200
    assert admin_client.get("/api/auth/me").status_code == 401


# ---------- 权限拦截 ----------


def test_anonymous_write_401(client):
    r = client.post("/api/nodes", json={
        "id": "x", "group_id": "g3", "layer_id": "policy", "name": "x", "x": 1, "y": 1,
    })
    assert r.status_code == 401


def test_anonymous_read_200(client):
    assert client.get("/api/atlas/graph").status_code == 200
    assert client.get("/api/health").status_code == 200


def test_viewer_write_403(viewer_client):
    r = viewer_client.post("/api/nodes", json={
        "id": "x", "group_id": "g3", "layer_id": "policy", "name": "x", "x": 1, "y": 1,
    })
    assert r.status_code == 403


def test_viewer_read_200(viewer_client):
    assert viewer_client.get("/api/atlas/graph").status_code == 200


def test_viewer_cannot_manage_users(viewer_client):
    assert viewer_client.get("/api/auth/users").status_code == 403
    assert viewer_client.post("/api/auth/users", json={
        "username": "sneaky", "password": "password-123", "role": "admin",
    }).status_code == 403


# ---------- 用户管理 ----------


def test_create_and_delete_user(admin_client):
    r = admin_client.post("/api/auth/users", json={
        "username": "tmp_user", "password": "password-123", "role": "viewer",
    })
    assert r.status_code == 201
    assert r.json()["role"] == "viewer"
    assert admin_client.delete("/api/auth/users/tmp_user").status_code == 200


def test_duplicate_username_409(admin_client):
    admin_client.post("/api/auth/users", json={
        "username": "dup_user", "password": "password-123", "role": "viewer",
    })
    r = admin_client.post("/api/auth/users", json={
        "username": "dup_user", "password": "password-123", "role": "viewer",
    })
    assert r.status_code == 409
    admin_client.delete("/api/auth/users/dup_user")


def test_short_password_rejected_422(admin_client):
    r = admin_client.post("/api/auth/users", json={
        "username": "shortpw", "password": "123", "role": "viewer",
    })
    assert r.status_code == 422


def test_cannot_demote_self(admin_client):
    r = admin_client.patch("/api/auth/users/admin", json={"role": "viewer"})
    assert r.status_code == 400
    assert admin_client.get("/api/auth/me").json()["role"] == "admin"


def test_cannot_delete_self(admin_client):
    assert admin_client.delete("/api/auth/users/admin").status_code == 400


def test_change_password_flow(admin_client):
    # 建一个临时用户，改它口令，用新口令登录
    admin_client.post("/api/auth/users", json={
        "username": "pw_user", "password": "old-password-123", "role": "viewer",
    })
    c2 = TestClient(admin_client.app)
    assert c2.post("/api/auth/login", json={"username": "pw_user", "password": "old-password-123"}).status_code == 200
    r = c2.post("/api/auth/password", json={
        "old_password": "old-password-123", "new_password": "new-password-456",
    })
    assert r.status_code == 200
    assert c2.post("/api/auth/login", json={"username": "pw_user", "password": "new-password-456"}).status_code == 200
    admin_client.delete("/api/auth/users/pw_user")


def test_change_password_wrong_old_400(admin_client):
    admin_client.post("/api/auth/users", json={
        "username": "pw_user2", "password": "old-password-123", "role": "viewer",
    })
    c2 = TestClient(admin_client.app)
    c2.post("/api/auth/login", json={"username": "pw_user2", "password": "old-password-123"})
    r = c2.post("/api/auth/password", json={
        "old_password": "totally-wrong", "new_password": "new-password-456",
    })
    assert r.status_code == 400
    admin_client.delete("/api/auth/users/pw_user2")


def test_deactivated_user_cannot_login(admin_client):
    admin_client.post("/api/auth/users", json={
        "username": "off_user", "password": "password-123", "role": "viewer",
    })
    admin_client.patch("/api/auth/users/off_user", json={"is_active": False})
    c2 = TestClient(admin_client.app)
    assert c2.post("/api/auth/login", json={"username": "off_user", "password": "password-123"}).status_code == 401
    admin_client.delete("/api/auth/users/off_user")
