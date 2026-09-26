"""pytest 共享 fixture：独立临时库 + TestClient + 已登录客户端。

每个测试函数各拿一个全新的 TestClient（function 作用域）。
不用 session 作用域的原因：某个测试执行登出会把共享 client 的 cookie 清掉，
污染后续所有测试（实测 37 个失败全是这么来的）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# 必须在 import app 之前设置，保证 config 指向临时库
_TMP_DB = Path(__file__).resolve().parent / "_test_atlas.db"
os.environ["ATLAS_DB"] = str(_TMP_DB)
os.environ["ATLAS_SEED"] = "1"
os.environ["ATLAS_ADMIN_USER"] = "admin"
os.environ["ATLAS_ADMIN_PASSWORD"] = "test-admin-password-123"
os.environ["ATLAS_SECRET_KEY"] = "test-secret-key-for-pytest-only"

from app.main import app  # noqa: E402

TEST_PASSWORD = "test-admin-password-123"


@pytest.fixture()
def client() -> TestClient:
    """未登录的客户端（每个测试一个全新实例）。"""
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def admin_client(client: TestClient) -> TestClient:
    """已登录 admin 的客户端。"""
    r = client.post("/api/auth/login", json={"username": "admin", "password": TEST_PASSWORD})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture()
def viewer_client(client: TestClient) -> TestClient:
    """已登录 viewer 的客户端；用完登出并删除临时用户。"""
    # 先用 admin 建账号（创建用户需要管理员权限）
    assert client.post("/api/auth/login",
                       json={"username": "admin", "password": TEST_PASSWORD}).status_code == 200
    assert client.post("/api/auth/users", json={
        "username": "tmp_viewer", "password": "viewer-pass-123", "role": "viewer",
    }).status_code == 201
    client.post("/api/auth/logout")
    r = client.post("/api/auth/login", json={"username": "tmp_viewer", "password": "viewer-pass-123"})
    assert r.status_code == 200, r.text
    yield client
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "admin", "password": TEST_PASSWORD})
    client.delete("/api/auth/users/tmp_viewer")
