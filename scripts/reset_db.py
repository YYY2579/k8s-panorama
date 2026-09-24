#!/usr/bin/env python
"""删库重建 + 重新灌种子数据。

用法：
    python scripts/reset_db.py
会删除 backend/data/atlas.db，然后按 ORM 模型建表并灌入种子数据。
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from app.config import DB_PATH  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.models import Base  # noqa: E402
from app.seed import seed_if_empty  # noqa: E402


def main() -> int:
    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"已删除旧库：{DB_PATH}")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seeded = seed_if_empty(db)
    finally:
        db.close()
    print(f"已建表并{'灌入种子数据' if seeded else '（未灌入）'}：{DB_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
