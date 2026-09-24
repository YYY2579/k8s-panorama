"""启动入口：python run.py

等价于：python -m uvicorn app.main:app --reload --port 8000
"""
import uvicorn

from app.config import HOST, PORT, RELOAD

if __name__ == "__main__":
    print(f"[atlas] 启动中 -> http://{HOST}:{PORT}   (接口文档 /docs)")
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=RELOAD, log_level="info")
