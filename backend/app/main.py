"""FastAPI 应用入口。

启动时：建表 → 首次灌种子 → 确保有管理员 → 挂载路由 → 同源托管前端静态目录。
使用 lifespan 上下文管理生命周期（FastAPI 0.93+ 推荐，替代已弃用的 on_event）。
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import crud, models  # noqa: F401  （确保模型被导入，迁移才能看到全部表）
from .bootstrap import ensure_admin, ensure_migration_state, upgrade_schema
from .config import API_PREFIX, CORS_ORIGINS, DATABASE_URL, SEED_ON_STARTUP, STATIC_DIR
from .db import SessionLocal, engine, get_db
from .routers import atlas, audit, auth, edges, groups, io, layers, nodes, notes, sops, yamls
from .seed import seed_if_empty


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """启动：确保迁移状态 + 升级到最新 + 首次灌种子 + 确保管理员。"""
    state = ensure_migration_state()
    if state != "already-versioned":
        upgrade_schema()
    db = SessionLocal()
    try:
        if SEED_ON_STARTUP and seed_if_empty(db):
            print(f"[atlas] 首次启动：已灌入种子数据 -> {DATABASE_URL}")
        ensure_admin(db)
    finally:
        db.close()
    yield
    # 关闭阶段可在此释放资源（如 flush 审计、关闭连接池）


def _run_migrations() -> None:
    """保留给脚本调用：确保状态 + 升级。"""
    ensure_migration_state()
    upgrade_schema()


app = FastAPI(
    title="K8s Panorama API",
    description="Kubernetes 全景架构知识图谱 —— 后端真实实现，数据持久化在 SQLite。",
    version="1.1.0",
    lifespan=lifespan,
)

# CORS：前端用 python -m http.server 单独起（5173）时需要
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ValueError)
async def _value_error_handler(_request: Request, exc: ValueError):
    """路由里抛出的 ValueError 统一转成 400。"""
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# ---------------- 路由注册 ----------------
for r in (atlas, groups, nodes, edges, layers, notes, sops, yamls, audit, auth, io):
    app.include_router(r.router, prefix=API_PREFIX)


@app.get(f"{API_PREFIX}/ping", tags=["图谱"], summary="最简探活")
def ping():
    return {"pong": True}


@app.get(f"{API_PREFIX}/health", tags=["图谱"], summary="健康检查与库内计数")
def health(db: Session = Depends(get_db)):
    """/api/atlas/health 的别名，方便直接探活。"""
    counts = crud.counts(db)
    counts["users"] = db.scalar(select(func.count()).select_from(models.User)) or 0
    return {"status": "ok", "database": "sqlite", "counts": counts}


# ---------------- 同源托管前端（放最后，避免覆盖 /api） ----------------
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="frontend")
else:  # pragma: no cover
    print(f"[atlas] 未找到前端目录：{STATIC_DIR}，将以纯 API 模式运行")
