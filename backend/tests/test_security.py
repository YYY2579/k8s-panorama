"""口令哈希与会话签名的单元测试。"""
from __future__ import annotations

import pytest

from app.security import (
    COOKIE_MAX_AGE,
    generate_password,
    hash_password,
    make_session_token,
    read_session_token,
    verify_password,
)

# ---------- 口令哈希 ----------


def test_hash_password_format():
    h = hash_password("correct horse battery")
    assert h.startswith("pbkdf2_sha256$260000$")
    parts = h.split("$")
    assert len(parts) == 4
    assert len(bytes.fromhex(parts[2])) == 16          # 128-bit salt


def test_verify_password_ok():
    h = hash_password("S3cret!")
    assert verify_password("S3cret!", h) is True


def test_verify_password_wrong():
    h = hash_password("S3cret!")
    assert verify_password("wrong", h) is False


def test_hash_is_salted():
    """同一口令两次哈希结果必须不同（随机盐）。"""
    a, b = hash_password("same"), hash_password("same")
    assert a != b
    assert verify_password("same", a) and verify_password("same", b)


def test_verify_password_rejects_garbage():
    for bad in ["", "not-a-hash", "pbkdf2_sha256$abc$xx$yy", "md5$1$2$3", "pbkdf2_sha256$260000$zz$yy"]:
        assert verify_password("x", bad) is False


def test_generate_password_length_and_charset():
    p = generate_password(20)
    assert len(p) == 20
    assert p.isalnum()                      # 只含字母数字
    assert generate_password() != generate_password()


# ---------- 会话 token ----------


def test_session_roundtrip():
    tok = make_session_token("7", "admin")
    data = read_session_token(tok)
    assert data["uid"] == "7"
    assert data["role"] == "admin"
    assert "iat" in data


def test_session_tampered_signature_rejected():
    tok = make_session_token("7", "admin")
    tampered = tok[:-4] + ("AAAA" if not tok.endswith("AAAA") else "BBBB")
    assert read_session_token(tampered) is None


def test_session_garbage_rejected():
    for bad in ["", "garbage", "a.b.c", "####"]:
        assert read_session_token(bad) is None


def test_session_expired_rejected():
    """手工构造一个很久以前签发的 token，应被判为过期。"""
    from itsdangerous import URLSafeSerializer
    from app.security import SECRET_KEY

    ser = URLSafeSerializer(SECRET_KEY, salt="atlas-session-v1")
    old = ser.dumps({"uid": "1", "role": "admin", "iat": "2020-01-01T00:00:00+00:00"})
    assert read_session_token(old) is None


def test_session_missing_fields_rejected():
    from itsdangerous import URLSafeSerializer
    from app.security import SECRET_KEY

    ser = URLSafeSerializer(SECRET_KEY, salt="atlas-session-v1")
    assert read_session_token(ser.dumps({"uid": "1"})) is None      # 缺 role
    assert read_session_token(ser.dumps({"role": "admin"})) is None  # 缺 uid
    assert read_session_token(ser.dumps(["not", "a", "dict"])) is None
