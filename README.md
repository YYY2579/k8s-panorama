# K8s Panorama

**Kubernetes 全景架构知识图谱**

一个可交互的 K8s 组件关系知识图谱系统：把 41 个核心组件、42 条调用关系按分层组织成一张可缩放的知识图谱，
并为每个组件附带知识条目、排障 SOP 与验证命令。数据持久化在 SQLite，支持完整的增删改查与状态流转。

[![CI](https://github.com/YYY2579/k8s-panorama/actions/workflows/ci.yml/badge.svg)](https://github.com/YYY2579/k8s-panorama/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)

- 仓库：<https://github.com/YYY2579/k8s-panorama>
- 技术栈：FastAPI · SQLAlchemy 2.0 · SQLite · Pydantic v2 · 原生前端（零依赖）
- 部署：[宿主机](deploy/bare-metal.md) · [Docker](deploy/docker.md)

---

## 功能特性

| 能力 | 说明 |
|---|---|
| 交互式图谱 | 8 个分层分组、8 种分类着色、42 条带标签的连线；支持缩放、平移、节点拖动 |
| 组件知识卡 | 点击组件展示关键属性、基础信息、上下游关系、关联知识条目与验证命令 |
| 图层过滤 | 8 个分类可独立显隐，同时驱动图例、左栏过滤器与连线配色 |
| 视图聚焦 | 6 种视角（全景 / 控制面 / 节点 / 网络 / 工作负载 / 安全存储）一键聚焦 |
| 完整 CRUD | 组件、关系、分组、知识条目、排障 SOP、YAML 片段均可在界面增删改查 |
| 状态流转 | 知识条目与 SOP 支持 `draft → review → published`，可归档与恢复 |
| 全文检索 | 跨组件 / 知识 / SOP 的关键词检索，支持中英文 |
| 链路分析 | 「网络链路」页签基于 BFS 计算两个组件间的真实最短路径 |
| 审计日志 | 所有写操作自动留痕，可通过接口查询 |
| 导入导出 | 一键导出全库 JSON，支持 `merge` / `replace` 两种方式回灌 |
| 登录与权限 | 会话 cookie 登录；`admin` 可写、`viewer` 只读；未登录 401、权限不足 403 |
| 三种数据源 | 顶栏一键切换：**知识库**（我的数据）/ **官方全景**（出厂数据）/ **集群实况**（接入 K8s） |
| 深浅主题 | 顶栏一键切换，默认跟随系统；选择记在本地，只影响外观不影响数据 |
| 集群接入 | 只读探针采集真实集群，按全景槽位填充运行状态；异常高亮、未检测到置灰 |
| 实况命令面板 | 右栏命令按集群实况自动参数化（填入真实对象名），异常时定位命令置顶，写操作加标记 |
| 三种数据源 | 顶栏一键切换：**知识库**（我的数据）/ **官方全景**（出厂数据）/ **集群实况**（接入 K8s） |
| 集群接入 | 只读探针采集真实集群，按全景槽位填充运行状态；异常高亮、未检测到置灰 |
| 实况命令面板 | 右栏命令按集群实况自动参数化（填入真实对象名），异常时定位命令置顶，写操作加标记 |
| 操作可追溯 | 每次写操作记录操作者（actor），审计日志支持按实体 / 操作者过滤 |
| 数据库迁移 | Alembic 管理 schema，加字段走"生成迁移 → upgrade"，不再靠删库重建 |

页面上的每一个节点、每一条连线、每一段知识正文都来自数据库；新建 / 编辑 / 删除都会真实写入
`backend/data/atlas.db` 并在 `audit_log` 表留下记录。

## 快速开始

### 环境要求

| 项 | 要求 |
|---|---|
| Python | 3.11 或更高（开发验证版本 3.13） |
| 磁盘 | ≥ 100 MB |
| 端口 | 默认 8000，可配置 |

无需数据库服务 —— SQLite 即文件，随项目自带。

### 安装与启动

```bash
git clone https://github.com/YYY2579/k8s-panorama.git
cd k8s-panorama
python -m pip install -r requirements.txt

cd backend
python run.py
```

首次启动会自动建库并灌入种子数据（41 个组件 / 42 条关系 / 8 个分组 / 8 个分类 / 3 条知识 / 2 条 SOP / 2 条 YAML）。

**首次登录**：启动时会自动创建管理员账号。

- 口令取自环境变量 `ATLAS_ADMIN_PASSWORD`（推荐，见下方配置表）
- 未设置时随机生成 16 位口令，**只打印一次**到启动日志，请立即登录后在「用户管理」里改掉

```bash
# 推荐：显式指定口令
ATLAS_ADMIN_PASSWORD="your-strong-password" python run.py
```

读接口（图谱、检索、健康检查）无需登录；写接口需要 `admin`。

### 访问

| 地址 | 说明 |
|---|---|
| <http://127.0.0.1:8000/> | 前端界面（后端同源托管） |
| <http://127.0.0.1:8000/docs> | OpenAPI 交互式接口文档 |
| <http://127.0.0.1:8000/api/health> | 健康检查与库内计数 |

> Windows 上若 `python` 指向不明版本，使用 `py -3 -m pip install -r requirements.txt`。

## 配置

所有配置项均可通过环境变量覆盖，均有默认值，零配置即可运行。

| 变量 | 默认值 | 说明 |
|---|---|---|
| `ATLAS_DB` | `backend/data/atlas.db` | SQLite 文件路径 |
| `ATLAS_PORT` | `8000` | 监听端口 |
| `ATLAS_HOST` | `127.0.0.1` | 监听地址 |
| `ATLAS_CORS` | `http://127.0.0.1:5173,http://localhost:5173,...` | 允许的跨域源，逗号分隔 |
| `ATLAS_SEED` | `1` | 设为 `0` 则启动时不灌种子数据 |
| `ATLAS_RELOAD` | `1` | `python run.py` 是否开启自动重载 |
| `ATLAS_ADMIN_USER` | `admin` | 首启创建的管理员用户名 |
| `ATLAS_ADMIN_PASSWORD` | 随机生成 | 首启管理员口令；**生产环境必须显式设置** |
| `ATLAS_SECRET_KEY` | 随机生成 | 会话 cookie 签名密钥；轮转它等于让所有会话失效 |
| `ATLAS_SESSION_TTL` | `43200`（12 小时） | 会话有效期，秒 |
| `ATLAS_K8S_API` | 未设置 | 集群 apiserver 地址，如 `https://192.168.1.10:6443` |
| `ATLAS_K8S_TOKEN` | 空 | ServiceAccount token（Bearer） |
| `ATLAS_KUBECONFIG` | `~/.kube/config` | 未设 `ATLAS_K8S_API` 时从 kubeconfig 读取 |
| `ATLAS_K8S_TIMEOUT` | `5`（秒） | 单次 API 请求超时 |
| `ATLAS_K8S_CACHE_TTL` | `10`（秒） | 集群快照缓存时间 |
| `ATLAS_K8S_VERIFY_TLS` | `1` | 自签证书可设 `0`（仅限内网） |
| `ATLAS_K8S_API` | 未设置 | 集群 apiserver 地址，如 `https://192.168.1.10:6443` |
| `ATLAS_K8S_TOKEN` | 空 | ServiceAccount token（Bearer） |
| `ATLAS_KUBECONFIG` | `~/.kube/config` | 未设 `ATLAS_K8S_API` 时从 kubeconfig 读取 |
| `ATLAS_K8S_TIMEOUT` | `5`（秒） | 单次 API 请求超时 |
| `ATLAS_K8S_CACHE_TTL` | `10`（秒） | 集群快照缓存时间 |
| `ATLAS_K8S_VERIFY_TLS` | `1` | 自签证书可设 `0`（仅限内网） |

```bash
ATLAS_PORT=9000 python run.py              # bash
$env:ATLAS_PORT="9000"; python run.py      # PowerShell
```

重置数据库：`python scripts/reset_db.py`（删库 → 建表 → 重新灌种子）。

## 项目结构

```
k8s-panorama/
├── README.md                  产品说明（本文件）
├── requirements.txt           依赖清单
├── backend/
│   ├── run.py                 启动入口
│   ├── data/atlas.db          SQLite 数据库（运行时生成，不入版本库）
│   └── app/
│       ├── config.py          配置
│       ├── db.py              engine / SessionLocal / get_db
│       ├── models.py          ORM 模型（10 张表）
│       ├── schemas.py         Pydantic 入参/出参
│       ├── crud.py            数据库读写（唯一写库入口，自动写审计）
│       ├── seed.py            种子数据
│       ├── main.py            应用装配：CORS、路由、静态托管、启动钩子
│       └── routers/           atlas | nodes | edges | groups | layers | notes | sops | yamls | audit | io
├── frontend/
│   ├── index.html
│   ├── styles.css            排版令牌集中于 :root
│   └── app.js                全部数据来自 /api，无写死内容
├── deploy/                    部署
│   ├── README.md             部署总览与通用事前说明
│   ├── bare-metal.md         宿主机部署（systemd + nginx）
│   ├── docker.md             Docker 部署
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── systemd/k8s-panorama.service
│   └── nginx/k8s-panorama.conf
├── scripts/
│   ├── test_api.py           端到端接口测试
│   ├── reset_db.py           重建数据库（删表 → 迁移 → 灌种子）
│   └── _gen_seed.py          从图谱数据生成种子文件
├── backend/app/cluster/      集群接入模块（只读探针，独立子包）
├── backend/app/cluster/      集群接入模块（只读探针，独立子包）
├── backend/migrations/       Alembic 迁移脚本
├── backend/tests/            pytest 单元测试（73 个用例）
└── .github/workflows/ci.yml  CI：pytest + 端到端测试
├── docs/
│   ├── DEVELOPMENT.md        开发说明与扩展指南
│   └── CHANGELOG.md          变更记录与验收证据
└── tests/
    └── manual_steps.md       手工验收步骤
```

## 技术栈

| 层 | 选型 | 理由 |
|---|---|---|
| 后端框架 | FastAPI | 自带 OpenAPI 文档，Pydantic 强校验，写 CRUD 效率高 |
| 数据访问 | SQLAlchemy 2.0 ORM | 模型即表结构；换 PostgreSQL 只改连接串 |
| 存储 | SQLite | 零安装、文件即库，满足持久化且便于备份 |
| 校验 | Pydantic v2 | 非法请求直接 422，避免脏数据入库 |
| 服务 | Uvicorn | ASGI 服务器 |
| 前端 | 原生 HTML/CSS/JS | 零构建步骤，后端同源托管即可打开 |

未引入前端框架的原因：本项目后端复杂度占比更高，引入构建链对"能本地跑起来"是负收益；
前端已按数据 / 渲染 / 交互分层，后续迁框架成本可控。

## 数据模型

10 张表：

| 表 | 作用 |
|---|---|
| `layer` | 分类 / 图层（8 项，驱动图例、过滤器、连线配色） |
| `atlas_group` | 分组容器（8 个，编号 ①~⑨，跳过 ⑥ 以保持与原始图谱一致） |
| `node` | 组件节点 |
| `node_field` | 组件关键字段（一对多） |
| `edge` | 组件关系 |
| `note` | 知识条目（含状态） |
| `sop` | 排障 SOP（含状态） |
| `sop_step` | SOP 步骤（一对多） |
| `yaml_snippet` | YAML 片段 |
| `audit_log` | 审计日志 |

集群状态**不落库**：只进内存 TTL 缓存（默认 10 秒），需要历史对比时再考虑独立快照表。
知识库数据与集群数据物理分离，互不写入。

集群状态**不落库**：只进内存 TTL 缓存（默认 10 秒），需要历史对比时再考虑独立快照表。
知识库数据与集群数据物理分离，互不写入。

状态流转规则：

```
draft ──publish──> review ──approve──> published
  └────────────── archive ───────────> archived ──restore──> draft
```

## API 概览

完整清单见 <http://127.0.0.1:8000/docs>。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查与库内计数 |
| GET | `/api/atlas/graph` | 一次返回分组 / 组件 / 关系 / 图层 |
| GET | `/api/atlas/search?q=` | 跨组件 / 知识 / SOP 检索 |
| GET | `/api/atlas/views` | 视图定义 |
| GET/POST/PATCH/DELETE | `/api/groups[/{id}]` | 分组增删改查 |
| GET/POST/PATCH/DELETE | `/api/nodes[/{id}]` | 组件增删改查（含字段） |
| GET/POST/PATCH/DELETE | `/api/edges[/{id}]` | 关系增删改查 |
| GET/PATCH | `/api/layers[/{id}]` | 图层列表 / 修改 |
| GET/POST/PATCH/DELETE | `/api/notes[/{slug}]` | 知识条目增删改查 |
| POST | `/api/notes/{slug}/transition` | 状态流转 |
| GET/POST/PATCH/DELETE | `/api/sops[/{symptom}]` | 排障 SOP 增删改查 |
| POST | `/api/sops/{symptom}/transition` | 状态流转 |
| GET/POST/PATCH/DELETE | `/api/yamls[/{id}]` | YAML 片段增删改查 |
| GET | `/api/audit` | 审计日志（支持 `entity` / `actor` 过滤） |
| GET | `/api/io/export` | 导出全库 JSON |
| POST | `/api/io/import?mode=` | 导入 JSON（`merge` / `replace`） |
| POST | `/api/auth/login` · `/api/auth/logout` · `GET /api/auth/me` | 登录 / 登出 / 当前用户 |
| GET/POST/PATCH/DELETE | `/api/auth/users[/{username}]` | 用户管理（仅 admin） |
| POST | `/api/auth/password` | 修改自己的口令 |
| GET | `/api/cluster/status` | 集群可达性 + 全部组件实况标注（需登录） |
| GET | `/api/cluster/components` | 组件 ID → 状态列表 |
| GET | `/api/cluster/nodes` | Node 汇总（Ready 比例、异常原因） |
| GET | `/api/cluster/workloads` | 工作负载汇总（期望 vs 就绪副本） |
| GET | `/api/atlas/official` | 出厂概念图谱（来自种子数据，不受编辑影响） |
| GET | `/api/cluster/status` | 集群可达性 + 全部组件实况标注（需登录） |
| GET | `/api/cluster/components` | 组件 ID → 状态列表 |
| GET | `/api/cluster/nodes` | Node 汇总（Ready 比例、异常原因） |
| GET | `/api/cluster/workloads` | 工作负载汇总（期望 vs 就绪副本） |
| GET | `/api/atlas/official` | 出厂概念图谱（来自种子数据，不受编辑影响） |

示例：

```bash
curl http://127.0.0.1:8000/api/health

curl -X POST http://127.0.0.1:8000/api/nodes \
  -H "Content-Type: application/json" \
  -d '{"id":"demo","group_id":"g3","layer_id":"policy","name":"示例组件",
       "kind":"示例","summary":"一句话","cmd":"kubectl get pods","x":10,"y":10,"fields":[]}'

curl "http://127.0.0.1:8000/api/audit?limit=5"
```

## 测试

```bash
# 服务运行于 8000 端口的前提下
python scripts/test_api.py
```

脚本会真实请求后端，逐条打印 `PASS/FAIL`，覆盖组件 / 关系 / 分组 / 知识条目 / SOP / YAML 的
完整 CRUD、状态流转（含非法流转拦截）、审计留痕、导出导入，并在结束时清理自身创建的测试数据。
当前版本 **51 项断言全部通过**（含管理员登录），完整输出见 [`docs/acceptance-test-output.txt`](docs/acceptance-test-output.txt)。

> 写接口需要登录，运行前请设置 `ATLAS_ADMIN_PASSWORD` 为后端 admin 口令。

### 单元测试

```bash
pytest backend/tests -q
```

73 个用例，覆盖口令哈希、会话签名与篡改检测、角色拦截、CRUD、状态流转、
导入导出的事务回滚。测试使用独立临时库，不碰 `backend/data/atlas.db`。

### 持续集成

推送或提 PR 时 GitHub Actions 自动执行：安装依赖 → `pytest` → 启动后端 → 端到端测试。
状态见仓库首页徽章。

浏览器侧的手工验收步骤见 [`tests/manual_steps.md`](tests/manual_steps.md)，其中包含
"重启后端后数据仍在"的持久化验证。

## 接入自己的 K8s 集群

集群接入是**独立模块、只读**：后端只发 GET，代码里不存在写方法；未连接时其他功能零影响。

### 方式一：直接指定（内网/自签证书最省事）

```bash
ATLAS_K8S_API="https://192.168.1.10:6443" \
ATLAS_K8S_TOKEN="<ServiceAccount token>" \
ATLAS_K8S_VERIFY_TLS=0 \
python run.py
```

### 方式二：kubeconfig

```bash
export KUBECONFIG=~/.kube/config
python run.py        # 未设 ATLAS_K8S_API 时自动读 kubeconfig
```

### 最小 RBAC（只读够用）

```bash
kubectl create serviceaccount atlas-ro -n kube-system
kubectl create clusterrolebinding atlas-ro \
  --clusterrole=view --serviceaccount=kube-system:atlas-ro
kubectl -n kube-system create token atlas-ro     # 有效期默认 1 小时
# 要长期有效需配 Secret 或调整 token 过期策略
```

`view` 这个内置 ClusterRole 已覆盖本项目用到的全部只读路径
（nodes/pods/services/endpointslices/deployments/networkpolicies/storageclasses 等）。

### 没有集群？先用模拟器练手

```bash
python scripts/mock_k8s.py --port 18081          # 另开一个终端
ATLAS_K8S_API="http://127.0.0.1:18081" python run.py
```

`mock_k8s.py` 会返回真实结构的 K8s JSON，并刻意制造一个 NotReady 节点、一个 Pending Pod、
一个 CrashLoopBackOff 容器，Gateway API 返回 404 —— 用来验证异常高亮与降级链路。

### 连接后能看到什么

顶栏把数据源切到「集群实况」：

- 全景槽位按四态填充：**在位**（分类色）/ **异常**（琥珀色脉冲）/ **未检测到**（置灰虚线）/ **采集不到**（半透明）
- 概念连线任一端异常 → 转琥珀加粗，直接看出哪条链路出问题
- 右栏「集群实况」卡片显示汇总（如 Node `就绪 1/2`、Pod `Pending×1`）
- 右栏「常用命令」已填入真实对象名，如 `kubectl describe node node-2`，点击即复制
- 顶栏徽标显示 `集群已连接 · N 项异常`

集群不可达时返回 503 并自动降级为知识库视图，其余功能不受影响。

## 部署

两种方式，事前准备与注意事项在各自文档开头说明：

- **宿主机部署**：[`deploy/bare-metal.md`](deploy/bare-metal.md) —— 含 systemd 单元、nginx 反代、备份恢复与升级
- **Docker 部署**：[`deploy/docker.md`](deploy/docker.md) —— 含 Dockerfile、Compose、数据卷备份

```bash
# Docker 快速启动
docker compose -f deploy/docker-compose.yml up -d --build
```

## 文档索引

| 文档 | 内容 |
|---|---|
| [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) | 代码分层、数据流、如何扩展、代码约定 |
| [`docs/CHANGELOG.md`](docs/CHANGELOG.md) | 版本变更与验收证据 |
| [`deploy/README.md`](deploy/README.md) | 部署总览与通用事前说明 |
| [`tests/manual_steps.md`](tests/manual_steps.md) | 手工验收步骤 |

## 已知限制

1. **鉴权较简**。已有登录与 admin/viewer 两级角色，但无密码强度策略、无登录限流、无审计导出。
   暴露到公网前建议在反向代理层再加访问控制与限流。
2. **不连接真实 K8s 集群**。界面中的 `kubectl` 命令供复制到本地终端执行，后端不执行任何 shell 命令。
3. **SQLite 单文件**。并发写入能力有限；需要多写并发时改 `config.DATABASE_URL` 为 PostgreSQL 即可，ORM 层无需改动。
4. 种子数据中的知识条目、排障 SOP、YAML 片段为示例内容，可在界面上直接编辑替换。

## 许可证

MIT
