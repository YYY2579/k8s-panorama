"""全局配置：数据库路径、服务端口、CORS、静态目录。

所有值都可用环境变量覆盖，方便不同机器直接跑。
"""
import os
from pathlib import Path

# backend/app/config.py -> backend/
BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent

# ---------------- 数据库 ----------------
DEFAULT_DB = BACKEND_DIR / "data" / "atlas.db"
DB_PATH = Path(os.getenv("ATLAS_DB", str(DEFAULT_DB)))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"

# ---------------- 服务 ----------------
HOST = os.getenv("ATLAS_HOST", "127.0.0.1")
PORT = int(os.getenv("ATLAS_PORT", "8000"))
RELOAD = os.getenv("ATLAS_RELOAD", "1") == "1"

# ---------------- CORS ----------------
# 前端若用 python -m http.server 单独起（默认 5173），需要跨域
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "ATLAS_CORS",
        "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:8000,http://localhost:8000",
    ).split(",")
    if o.strip()
]

# ---------------- 其它 ----------------
SEED_ON_STARTUP = os.getenv("ATLAS_SEED", "1") == "1"
API_PREFIX = "/api"
STATIC_DIR = PROJECT_DIR / "frontend"
