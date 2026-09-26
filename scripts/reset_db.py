#!/usr/bin/env python
"""重建数据库：删库 → alembic upgrade head 建表 → 灌种子数据。

用法：
    python scripts/reset_db.py

注意：这会删除 backend/data/atlas.db 里的全部数据。开发期工具。
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
BACKEND = PROJECT / "backend"
sys.path.insert(0, str(BACKEND))

from app.config import DB_PATH, SEED_ON_STARTUP  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.seed import seed_if_empty  # noqa: E402


def run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{DB_PATH.as_posix()}")
    command.upgrade(cfg, "head")


def main() -> int:
    # 先删表再删文件：直接删文件在某些环境会被安全策略拦截，
    # 而 drop_all 走的是 SQL，稳定可控
    from app import models  # noqa: F401  （确保模型已注册）
    from app.db import Base, engine

    Base.metadata.drop_all(bind=engine)
    print("已删除全部业务表")

    if DB_PATH.exists():
        try:
            DB_PATH.unlink()
            print(f"已删除旧库文件：{DB_PATH}")
        except OSError as exc:
            print(f"旧库文件删除失败（可忽略，表已清空）：{exc}")

    run_migrations()
    print(f"已按迁移建表：{DB_PATH}")

    if SEED_ON_STARTUP:
        db = SessionLocal()
        try:
            seed_if_empty(db)
            print("已灌入种子数据")
        finally:
            db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
