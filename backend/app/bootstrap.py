"""首启引导：确保库里至少有一个可用的 admin 账号。

口令来源优先级：
1. 环境变量 ATLAS_ADMIN_PASSWORD（推荐，写在部署配置里）
2. 未设置 → 随机生成 16 位口令，只打印一次到启动日志

用户名默认 admin，可用 ATLAS_ADMIN_USER 覆盖。
只在"没有任何用户"时创建；已有用户则什么都不做（不会覆盖你改过的口令）。
"""
from __future__ import annotations

import os

from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from .db import Base, engine
from .models import User
from .security import generate_password, hash_password


def ensure_schema() -> list[str]:
    """对比 ORM 模型与实际表结构，缺列时 `ALTER TABLE ADD COLUMN`。

    背景：`create_all` 只建新表，不会给已存在的表加列。模型新增字段
    （例如 audit_log.actor）后，旧库上查询会直接报 `no such column` → 500。

    这是 Alembic 上线（M1c）前的兜底；接入迁移后本函数应移除。
    SQLite 的 ADD COLUMN 对 NOT NULL 列要求有默认值，这里统一补 `DEFAULT ''`。
    """
    insp = inspect(engine)
    added: list[str] = []
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing:
                continue
            ddl_type = col.type.compile(engine.dialect)
            if not col.nullable and col.server_default is None:
                ddl_type += " DEFAULT ''"
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {col.name} {ddl_type}"))
            added.append(f"{table.name}.{col.name}")
    return added


def ensure_migration_state() -> str:
    """让库进入可被 Alembic 管理的状态。

    返回：
      fresh            —— 空库，直接 upgrade 即可
      already-versioned—— 已有 alembic_version，正常 upgrade
      stamped          —— 旧库（有业务表但无版本表），先 stamp head 再 upgrade，
                          否则 upgrade 会因"表已存在"而失败

    这一条只为兼容"迁移上线之前建的库"；新库不会走到 stamped 分支。
    """
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    insp = inspect(engine)
    if insp.has_table("alembic_version"):
        return "already-versioned"

    backend_dir = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))
    cfg.set_main_option("sqlalchemy.url", str(engine.url))

    if insp.has_table("node"):          # 有业务表但没有版本表 → 旧库
        command.stamp(cfg, "head")
        print("[atlas] 检测到迁移上线前创建的旧库，已标记为当前版本（stamp head）")
        return "stamped"

    return "fresh"


def upgrade_schema() -> None:
    """把库升级到最新迁移版本。"""
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))
    cfg.set_main_option("sqlalchemy.url", str(engine.url))
    command.upgrade(cfg, "head")


def ensure_admin(db: Session) -> User | None:
    """无用户时创建管理员。返回新建的用户；已有用户返回 None。"""
    total = db.scalar(select(func.count()).select_from(User)) or 0
    if total:
        return None

    username = os.getenv("ATLAS_ADMIN_USER", "admin")
    password = os.getenv("ATLAS_ADMIN_PASSWORD") or generate_password()
    user = User(username=username, password_hash=hash_password(password), role="admin")
    db.add(user)
    db.commit()
    db.refresh(user)

    if os.getenv("ATLAS_ADMIN_PASSWORD"):
        print(f"[atlas] 已按环境变量创建管理员：{username}")
    else:
        print("[atlas] " + "=" * 56)
        print(f"[atlas] 首次启动，已创建管理员账号（请立即登录并修改口令）：")
        print(f"[atlas]   用户名：{username}")
        print(f"[atlas]   口  令：{password}")
        print("[atlas] " + "=" * 56)
    return user


def require_admin_for_script(db: Session) -> User:
    """供命令行脚本使用：没有 admin 就直接抛错，不静默创建。"""
    user = db.scalar(select(User).where(User.role == "admin").order_by(User.id))
    if not user:
        raise RuntimeError("库里没有管理员账号，请先启动一次服务完成引导")
    return user
