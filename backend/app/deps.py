"""FastAPI 依赖：当前登录用户、角色校验。

- `current_user`   —— 解析会话 cookie，未登录返回 401
- `require_admin`  —— 必须是 admin，否则 403
- `audit_actor`    —— 取操作者名字（总是已登录），供 crud 记录
"""
from __future__ import annotations

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from . import crud
from .db import get_db
from .models import User
from .security import COOKIE_NAME, read_session_token


def current_user(
    db: Session = Depends(get_db),
    token: str | None = Cookie(default=None, alias=COOKIE_NAME),
) -> User:
    """从签名 cookie 解析用户；任何一步不合法都按未登录处理（401）。"""
    if not token:
        raise HTTPException(401, "未登录")
    data = read_session_token(token)
    if not data:
        raise HTTPException(401, "会话无效或已过期，请重新登录")
    user = db.get(User, int(data["uid"]))
    if not user or not user.is_active:
        raise HTTPException(401, "账号不存在或已停用")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    """写操作专用：只有 admin 能过。"""
    if user.role != "admin":
        raise HTTPException(403, f"需要管理员权限（当前角色：{user.role}）")
    return user


def audit_actor(user: User = Depends(current_user)) -> str:
    """供 crud.audit 记录操作者。"""
    return user.username
