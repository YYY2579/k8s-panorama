# Docker 部署

> 适用：希望环境隔离、一键起停、便于迁移；目标机已安装 Docker。
> 若服务器已有 Python 环境、需要用 systemd 托管，请改用 [`bare-metal.md`](bare-metal.md)。

---

## 1. 环境依赖

| 项 | 要求 |
|---|---|
| Docker Engine | **20.10+**（本机 Docker CLI 版本 29.8.0，Compose v2） |
| Docker Compose | **v2**（`docker compose version` 能输出版本即可） |
| 架构 | `linux/amd64` 或 `linux/arm64`（基础镜像 `python:3.12-slim` 为多架构） |
| 端口 | 宿主机 `8000` 可被映射占用 |
| 磁盘 | ≥ 300 MB（镜像约 200 MB + 数据卷） |
| 权限 | 当前用户能执行 `docker` 命令（在 `docker` 组或使用 root） |

**无需在本机安装 Python 或任何依赖** —— 全部在镜像内。

## 2. 前置条件

1. 代码已就位：
   ```bash
   git clone https://github.com/YYY2579/k8s-panorama.git
   cd k8s-panorama
   ```
2. 宿主机端口 `8000` 未被占用：
   ```bash
   # Linux
   ss -ltnp | grep ':8000'
   # Windows PowerShell
   netstat -ano | findstr :8000
   ```
3. Docker daemon 正在运行：`docker info` 能正常返回。
4. 能访问 Docker Hub 拉取 `python:3.12-slim`；若不通需配置镜像加速器。

## 3. 注意事项

- **本服务无鉴权**。容器端口映射到宿主机后，任何能访问宿主机该端口的人都可增删改。
  生产环境**不要**映射到 `0.0.0.0`，可改用：
  ```yaml
  ports:
    - "127.0.0.1:8000:8000"     # 只监听本机回环
  ```
  再配合宿主机上的 nginx 反代加访问控制（见 `bare-metal.md` 第 6 节）。
- **数据在命名卷 `k8s-panorama-data` 里**，不在镜像里。`docker compose down` **不会**删卷，
  只有 `docker compose down -v` 才会删 —— 执行 `-v` 前务必确认已备份。
- 首次启动自动建库并灌种子数据；容器重建不会导致数据丢失（只要卷还在）。
- 容器内以非 root 用户 `atlas`（uid 10001）运行。
- 升级 = 重新构建镜像 + 重启容器，步骤见第 6 节。

## 4. 快速启动（推荐）

```bash
cd k8s-panorama
docker compose -f deploy/docker-compose.yml up -d --build
```

然后自检：

```bash
docker compose -f deploy/docker-compose.yml ps
curl http://127.0.0.1:8000/api/health
```

`/api/health` 返回 `{"status":"ok",...}` 即成功。浏览器打开 <http://127.0.0.1:8000/>。

## 5. 常用命令

```bash
# 查看状态与健康检查结果
docker compose -f deploy/docker-compose.yml ps

# 实时日志
docker compose -f deploy/docker-compose.yml logs -f

# 停止（保留数据卷）
docker compose -f deploy/docker-compose.yml down

# 停止并删除数据卷（危险！会丢数据）
docker compose -f deploy/docker-compose.yml down -v

# 重启
docker compose -f deploy/docker-compose.yml restart

# 进容器排查
docker compose -f deploy/docker-compose.yml exec atlas sh
```

## 6. 升级

```bash
cd k8s-panorama
git pull

# 1. 先备份数据卷（重要）
docker run --rm -v k8s-panorama-data:/data -v "$PWD":/backup alpine \
  cp /data/atlas.db /backup/atlas-$(date +%F).db

# 2. 重新构建并替换容器
docker compose -f deploy/docker-compose.yml up -d --build

# 3. 验证
curl http://127.0.0.1:8000/api/health
```

> Windows PowerShell 下 `$PWD` 与 `$(date ...)` 不可用，改用固定路径：
> `docker run --rm -v k8s-panorama-data:/data -v C:\backup:/backup alpine cp /data/atlas.db /backup/atlas-backup.db`

## 7. 不用 Compose，直接 docker run

```bash
# 构建（上下文是项目根）
docker build -f deploy/Dockerfile -t k8s-panorama:1.0.0 .

# 运行
docker run -d \
  --name k8s-panorama \
  -p 8000:8000 \
  -v k8s-panorama-data:/app/backend/data \
  --restart unless-stopped \
  k8s-panorama:1.0.0
```

## 8. 用绑定目录代替命名卷

如果希望数据库文件直接落在宿主机某个目录（便于直接拷贝备份）：

```bash
mkdir -p /data/k8s-panorama
docker run -d --name k8s-panorama -p 8000:8000 \
  -v /data/k8s-panorama:/app/backend/data \
  k8s-panorama:1.0.0
```

Windows PowerShell：

```powershell
mkdir C:\k8s-panorama-data
docker run -d --name k8s-panorama -p 8000:8000 `
  -v C:\k8s-panorama-data:/app/backend/data `
  k8s-panorama:1.0.0
```

## 9. 数据备份与恢复

```bash
# 备份：把命名卷里的库复制出来
docker run --rm -v k8s-panorama-data:/data -v "$PWD":/backup alpine \
  cp /data/atlas.db /backup/atlas-backup.db

# 恢复：把备份写回卷
docker compose -f deploy/docker-compose.yml down
docker run --rm -v k8s-panorama-data:/data -v "$PWD":/backup alpine \
  cp /backup/atlas-backup.db /data/atlas.db
docker compose -f deploy/docker-compose.yml up -d
```

## 10. 卸载

```bash
cd k8s-panorama
# 先备份！
docker run --rm -v k8s-panorama-data:/data -v "$PWD":/backup alpine cp /data/atlas.db /backup/

docker compose -f deploy/docker-compose.yml down -v   # 删容器 + 卷
docker rmi k8s-panorama:1.0.0
```

## 11. 故障排查

| 现象 | 排查命令 / 原因 |
|---|---|
| 容器反复重启 | `docker compose logs --tail=50`，常见是端口被占用（`ATLAS_PORT` 已改但端口映射没改） |
| `healthcheck` 显示 `starting` 很久 | 首次启动要建库 + 灌种子，`start_period` 已给 10s；再等等，或看日志确认没有报错 |
| 浏览器打开白屏 | 确认访问的是 `http://127.0.0.1:8000/`（后端同源托管前端），不是 `8000/api/...` |
| 修改代码后没生效 | 需要重新 `--build`；镜像不会热更新 |
| 拉取 `python:3.12-slim` 超时 | 配置 Docker 镜像加速器，或改用内网已有基础镜像并修改 `deploy/Dockerfile` 的 `FROM` |
