"""认证：登录 / 登出 / 当前用户 / 用户管理 / 改密码。"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import crud
from ..db import get_db
from ..deps import current_user, require_admin
from ..models import User
from ..schemas import (
    LoginIn, PasswordChangeIn, UserIn, UserOut, UserPatch,
)
from ..security import COOKIE_NAME, COOKIE_MAX_AGE, hash_password, make_session_token, verify_password

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login", response_model=UserOut, summary="登录")
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == payload.username))
    # 用户不存在与口令错误返回同一句话，避免暴露"哪些用户名存在"
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise_401()
    user.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(user)
    token = make_session_token(str(user.id), user.role)
    response.set_cookie(
        COOKIE_NAME, token,
        max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax", path="/",
    )
    crud.audit(db, "login", "user", user.username, f"role={user.role}")
    db.commit()
    return user


def raise_401():
    raise HTTPException(401, "用户名或口令错误")


@router.post("/logout", summary="登出")
def logout(response: Response, db: Session = Depends(get_db),
           user: User = Depends(current_user)):
    response.delete_cookie(COOKIE_NAME, path="/")
    crud.audit(db, "logout", "user", user.username, "")
    db.commit()
    return {"ok": True}


@router.get("/me", response_model=UserOut, summary="当前登录用户")
def me(user: User = Depends(current_user)):
    return user


# ---------------- 用户管理（仅 admin） ----------------
@router.get("/users", response_model=list[UserOut], summary="用户列表")
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return list(db.scalars(select(User).order_by(User.id)).all())


@router.post("/users", response_model=UserOut, status_code=201, summary="新建用户")
def create_user(payload: UserIn, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    if db.scalar(select(User).where(User.username == payload.username)):
        raise HTTPException(409, f"用户名已存在：{payload.username}")
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    crud.audit(db, "create", "user", payload.username, f"role={payload.role} by={admin.username}")
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{username}", response_model=UserOut, summary="改角色 / 停用 / 重置口令")
def update_user(username: str, payload: UserPatch, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    user = db.scalar(select(User).where(User.username == username))
    if not user:
        raise HTTPException(404, f"用户不存在：{username}")
    if payload.password:
        user.password_hash = hash_password(payload.password)
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    # 不许把自己降级或停用，避免管理员把自己锁在外面
    if user.id == admin.id and (payload.role == "viewer" or payload.is_active is False):
        raise HTTPException(400, "不能降级或停用当前登录的自己")
    crud.audit(db, "update", "user", username, f"by={admin.username}")
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{username}", summary="删除用户")
def delete_user(username: str, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    user = db.scalar(select(User).where(User.username == username))
    if not user:
        raise HTTPException(404, f"用户不存在：{username}")
    if user.id == admin.id:
        raise HTTPException(400, "不能删除当前登录的自己")
    db.delete(user)
    crud.audit(db, "delete", "user", username, f"by={admin.username}")
    db.commit()
    return {"deleted": 1, "id": username}


@router.post("/password", summary="修改自己的口令")
def change_password(payload: PasswordChangeIn, db: Session = Depends(get_db),
                    user: User = Depends(current_user)):
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(400, "原口令不正确")
    user.password_hash = hash_password(payload.new_password)
    crud.audit(db, "update", "user", user.username, "self password change")
    db.commit()
    return {"ok": True}
