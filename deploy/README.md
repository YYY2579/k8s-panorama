# 部署

本项目提供两种部署方式，按场景选择：

| 方式 | 适用场景 | 文档 |
|---|---|---|
| **宿主机部署** | 已有 Python 环境的 Linux 服务器；需要 systemd 托管、与其它服务共用端口策略 | [`bare-metal.md`](bare-metal.md) |
| **Docker 部署** | 希望环境隔离、一键起停、便于迁移；机器上已装 Docker | [`docker.md`](docker.md) |

## 两种方式都适用的事前说明

### 环境依赖

| 项 | 宿主机部署 | Docker 部署 |
|---|---|---|
| 运行时 | Python **3.11+**（开发验证版本 3.13） | Docker **20.10+** 与 Compose **v2+** |
| 包管理器 | pip | 无需本机 Python |
| 端口 | 默认 `8000`（可改） | 默认 `8000`（可改） |
| 磁盘 | ≥ 100 MB（含依赖与 SQLite 库） | ≥ 300 MB（含镜像层） |
| 权限 | 需要对部署目录的写权限 | Docker daemon 使用权限 |

### 前置条件

1. 已取得项目代码：`git clone https://github.com/YYY2579/k8s-panorama.git`
2. 目标端口未被占用（宿主机用 `ss -ltnp | grep :8000` 或 `netstat -ano | findstr :8000` 确认）
3. 若通过域名 + HTTPS 对外提供，需先准备好域名解析与证书（宿主机文档给出 nginx 反代示例）
4. 确认目标机器能访问 PyPI 或已配置内网镜像源（宿主机部署装依赖时需要）

### 注意事项（重要）

- **本项目无鉴权**。接口未做登录，任何能访问 `8000` 端口的人都能增删改。
  生产环境**必须**放在内网，或按 `bare-metal.md` 第 6 节的 nginx 反代加访问控制，不要直接暴露到公网。
- **数据是文件**：`backend/data/atlas.db`。宿主机部署要备份这个文件；
  Docker 部署要备份命名卷 `k8s-panorama-data`。
  备份的正确姿势是先停服务再拷贝，或用 SQLite 的 `VACUUM INTO` 在线备份。
- **升级步骤**：宿主机 `git pull` → 装依赖 → `systemctl restart`；
  Docker `docker compose build && docker compose up -d`。
  两种方式升级前都建议先备份数据库。
- **首次启动会自动灌种子数据**（41 个组件 / 42 条关系 / 8 个分组）。
  已有库不会重复灌入，不会覆盖你后来新增的内容。
- **后端不执行任何 shell 命令**。界面上的 `kubectl` 命令只给人复制到自己终端执行，
  这是有意的安全边界，部署时无需为此开放额外权限。

## 部署后自检（两种方式通用）

```bash
# 1. 进程健康
curl http://127.0.0.1:8000/api/health

# 2. 图谱数据真的从库里出来了
curl -s http://127.0.0.1:8000/api/atlas/graph \
  | python -c "import sys,json;d=json.load(sys.stdin);print(len(d['nodes']),'个组件 /',len(d['edges']),'条关系')"

# 3. 写操作真的落库（应返回 201）
curl -X POST http://127.0.0.1:8000/api/nodes \
  -H "Content-Type: application/json" \
  -d '{"id":"deploy-check","group_id":"g3","layer_id":"policy","name":"部署自检","kind":"临时","summary":"验证用","cmd":"kubectl get pods","x":10,"y":10,"fields":[]}'

# 4. 确认落库后删除
curl -X DELETE http://127.0.0.1:8000/api/nodes/deploy-check
```

## 相关文档

- 项目总览与本地开发：[`../README.md`](../README.md)
- 内部结构与二次开发：[`../docs/DEVELOPMENT.md`](../docs/DEVELOPMENT.md)
- 版本记录与验收证据：[`../docs/CHANGELOG.md`](../docs/CHANGELOG.md)
- 手工验收步骤：[`../tests/manual_steps.md`](../tests/manual_steps.md)
