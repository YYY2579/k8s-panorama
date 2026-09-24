# syntax=docker/dockerfile:1
#
# K8s Panorama 单容器镜像
# 构建上下文必须是项目根目录（compose 里已配 context: ..）
#
#   docker build -f deploy/Dockerfile -t k8s-panorama:1.0.0 .
#
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ATLAS_HOST=0.0.0.0 \
    ATLAS_PORT=8000 \
    ATLAS_SEED=1

WORKDIR /app/backend

# 依赖单独一层，改业务代码不必重装依赖
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r /app/requirements.txt \
 && useradd --system --uid 10001 --create-home atlas \
 && mkdir -p /app/backend/data \
 && chown -R atlas:atlas /app/backend/data

# 后端 + 前端静态文件（由 app.main 同源托管）+ 脚本
COPY backend/  /app/backend/
COPY frontend/ /app/frontend/
COPY scripts/  /app/scripts/

USER atlas

# SQLite 数据持久化到命名卷 / 绑定目录
VOLUME ["/app/backend/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=4).status==200 else 1)"

CMD ["python", "-m", "uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
