# 宿主机部署（Bare Metal / 虚拟机）

> 适用：已有 Python 环境的 Linux 服务器，需要用 systemd 托管进程、与其它服务共存。
> 如果你更希望环境隔离、一键起停，请改用 [`docker.md`](docker.md)。

---

## 1. 环境依赖

| 项 | 要求 | 说明 |
|---|---|---|
| 操作系统 | 任意主流 Linux（本文以 Ubuntu 22.04 / Rocky 9 为例） | Windows / macOS 同样可跑，只是 systemd 部分不适用 |
| Python | **3.11 或更高** | 开发与验证版本为 3.13；3.10 及以下不保证兼容 |
| pip | 与 Python 版本对应 | 用于安装 `requirements.txt` |
| SQLite | Python 自带，无需单独安装 | 数据库即文件，无外部服务 |
| 端口 | 默认 `8000`，可被本服务独占 | 通过 `ATLAS_PORT` 修改 |
| 磁盘 | ≥ 100 MB | 依赖约 60 MB，SQLite 库随使用增长 |
| 内存 | ≥ 128 MB | 单进程常驻 |

## 2. 前置条件

1. 代码已就位：
   ```bash
   sudo git clone https://github.com/YYY2579/k8s-panorama.git /opt/k8s-panorama
   ```
2. 端口未被占用：
   ```bash
   ss -ltnp | grep ':8000' || echo "端口空闲"
   ```
3. 有 root 或 sudo 权限（创建专用用户、写 systemd）。
4. 目标机能访问 PyPI，或已配置内网镜像源。若无法出网，需在有网机器上准备好 `venv` 一并拷贝。
5. 若需对外提供，域名解析与证书已准备好（见第 6 节）。

## 3. 注意事项

- **本服务无鉴权**。部署后任何能访问该端口的人都可增删改。生产环境请放在内网，
  或按第 6 节在 nginx 层加 IP 白名单 / Basic Auth。**不要直接暴露到公网。**
- **数据只有一份**：`backend/data/atlas.db`。定期备份它，详见第 7 节。
- 首次启动会自动建库并灌入种子数据；已有库不会重复灌入。
- 建议使用**专用非 root 用户**运行，不要用 root 起服务。
- 日志默认走 systemd journal；若需落盘日志，按第 5 节配置 `StandardOutput`。

## 4. 部署步骤

### 4.1 创建专用用户与目录

```bash
sudo useradd --system --home /opt/k8s-panorama --shell /usr/sbin/nologin atlas
sudo mkdir -p /opt/k8s-panorama
sudo chown atlas:atlas /opt/k8s-panorama
```

### 4.2 放置代码并创建虚拟环境

```bash
cd /opt/k8s-panorama
sudo -u atlas git clone https://github.com/YYY2579/k8s-panorama.git .
sudo -u atlas python3 -m venv venv
sudo -u atlas ./venv/bin/pip install --upgrade pip
sudo -u atlas ./venv/bin/pip install -r requirements.txt
```

### 4.3 验证能手动启动

```bash
sudo -u atlas ./venv/bin/python backend/run.py
# 另开终端验证：
curl http://127.0.0.1:8000/api/health
```

能返回 `{"status":"ok",...}` 后 `Ctrl+C` 停掉，继续下面的 systemd 配置。

### 4.4 配置 systemd 服务

复制仓库内现成单元文件：

```bash
sudo cp /opt/k8s-panorama/deploy/systemd/k8s-panorama.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now k8s-panorama
sudo systemctl status k8s-panorama
```

`deploy/systemd/k8s-panorama.service` 内容与本节等价，可直接参考：

```ini
[Unit]
Description=K8s Panorama - Kubernetes 全景架构知识图谱
After=network.target

[Service]
Type=simple
User=atlas
WorkingDirectory=/opt/k8s-panorama/backend
Environment=ATLAS_HOST=0.0.0.0
Environment=ATLAS_PORT=8000
Environment=ATLAS_SEED=1
ExecStart=/opt/k8s-panorama/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5
# 安全加固
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=/opt/k8s-panorama/backend/data

[Install]
WantedBy=multi-user.target
```

### 4.5 日常运维命令

```bash
sudo systemctl restart k8s-panorama     # 重启
sudo systemctl stop k8s-panorama        # 停止
journalctl -u k8s-panorama -f           # 看实时日志
journalctl -u k8s-panorama --since "1 hour ago"
```

## 5. 日志配置（可选）

默认日志进 systemd journal。如需落盘：

```bash
sudo mkdir -p /var/log/k8s-panorama && sudo chown atlas:atlas /var/log/k8s-panorama
```

在单元文件 `[Service]` 段加：

```ini
StandardOutput=append:/var/log/k8s-panorama/atlas.log
StandardError=append:/var/log/k8s-panorama/atlas.log
```

## 6. 对外访问：nginx 反代（可选但推荐）

**前置条件**：已安装 nginx；域名已解析到本机；若需 HTTPS，证书已就位。

`deploy/nginx/k8s-panorama.conf` 提供了一份可直接 include 的配置，关键内容：

```nginx
upstream k8s_panorama { server 127.0.0.1:8000; }

server {
    listen 80;
    server_name atlas.example.com;

    client_max_body_size 5m;   # 导入 JSON 时够用

    location / {
        proxy_pass         http://k8s_panorama;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    # 仅内网可访问（按需启用）
    # location / {
    #     allow 10.0.0.0/8;
    #     allow 192.168.0.0/16;
    #     deny  all;
    #     proxy_pass http://k8s_panorama;
    # }
}
```

启用方式：

```bash
sudo cp /opt/k8s-panorama/deploy/nginx/k8s-panorama.conf /etc/nginx/conf.d/
sudo nginx -t && sudo systemctl reload nginx
```

## 7. 备份与恢复

### 备份（推荐：在线备份，无需停服）

```bash
sudo -u atlas /opt/k8s-panorama/venv/bin/python - <<'PY'
import sqlite3
sqlite3.connect('/opt/k8s-panorama/backend/data/atlas.db').execute(
    "VACUUM INTO '/var/backups/atlas-$(date +%F).db'")
PY
```

> 注意：上面的 `$(date ...)` 在 heredoc 里不会展开。实际使用请写成固定文件名，
> 或直接用文件拷贝方式（需先停服）。

### 备份（简单方式：停服拷贝）

```bash
sudo systemctl stop k8s-panorama
sudo cp /opt/k8s-panorama/backend/data/atlas.db /var/backups/atlas-$(date +%F).db
sudo systemctl start k8s-panorama
```

### 恢复

```bash
sudo systemctl stop k8s-panorama
sudo cp /var/backups/atlas-2026-09-25.db /opt/k8s-panorama/backend/data/atlas.db
sudo chown atlas:atlas /opt/k8s-panorama/backend/data/atlas.db
sudo systemctl start k8s-panorama
```

## 8. 升级

```bash
sudo systemctl stop k8s-panorama
sudo -u atlas cp /opt/k8s-panorama/backend/data/atlas.db /var/backups/atlas-pre-upgrade.db
cd /opt/k8s-panorama
sudo -u atlas git pull
sudo -u atlas ./venv/bin/pip install -r requirements.txt
sudo systemctl start k8s-panorama
curl http://127.0.0.1:8000/api/health
```

## 9. 卸载

```bash
sudo systemctl disable --now k8s-panorama
sudo rm /etc/systemd/system/k8s-panorama.service
sudo systemctl daemon-reload
sudo rm -rf /opt/k8s-panorama          # 先确认已备份数据库
```
