"""认证与口令安全。

选型说明（写进文档，避免后来人问"为什么不用 bcrypt"）：
- 口令哈希用标准库 `hashlib.pbkdf2_hmac`（SHA-256，26 万次迭代），
  不引入 passlib/bcrypt —— 那两个在部分平台需要编译，纯标准库零依赖且足够安全。
- 会话用 `itsdangerist` 签名 cookie（无状态）：cookie 里只有 user_id 与 role，
  带签名与过期时间。不建 session 表，代价是"踢下线"只能靠轮换 SECRET_KEY。
  对内网/小团队工具这个取舍划算，若将来需要即时撤销再加 session 表。
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from itsdangerous import BadSignature, SignatureExpired, URLSafeSerializer

# ---------------- 配置 ----------------
SECRET_KEY = os.getenv("ATLAS_SECRET_KEY") or secrets.token_urlsafe(32)
COOKIE_NAME = "atlas_session"
COOKIE_MAX_AGE = int(os.getenv("ATLAS_SESSION_TTL", "43200"))   # 默认 12 小时
PBKDF2_ROUNDS = 260_000

_serializer = URLSafeSerializer(SECRET_KEY, salt="atlas-session-v1")


# ---------------- 口令哈希 ----------------
def hash_password(password: str, *, rounds: int = PBKDF2_ROUNDS) -> str:
    """返回 `pbkdf2_sha256$rounds$salt_hex$hash_hex`，自带算法与参数，便于日后升级。"""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return f"pbkdf2_sha256${rounds}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """常量时间比较；格式不符一律返回 False，不抛异常。"""
    try:
        algo, rounds, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


def generate_password(length: int = 16) -> str:
    """首启管理员口令：随机生成，只打印一次。"""
    alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


# ---------------- 会话 cookie ----------------
def make_session_token(user_id: str, role: str) -> str:
    payload = {
        "uid": user_id,
        "role": role,
        "iat": datetime.now(timezone.utc).isoformat(),
    }
    return _serializer.dumps(payload)


def read_session_token(token: str) -> dict | None:
    """验签 + 验过期。任何异常（篡改、过期、格式错）都返回 None，由调用方按未登录处理。"""
    try:
        data = _serializer.loads(token, max_age=COOKIE_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict) or "uid" not in data or "role" not in data:
        return None
    # 双保险：itsdangerous 的 max_age 已校验签名时间，这里再按 payload 里的 iat 校验一次，
    # 避免将来更换签名实现时漏掉过期判断
    iat = data.get("iat")
    if iat:
        try:
            issued = datetime.fromisoformat(iat)
            if issued.tzinfo is None:
                issued = issued.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - issued).total_seconds() > COOKIE_MAX_AGE:
                return None
        except ValueError:
            return None
    return data
