# K8s Panorama — Kubernetes 全景架构知识图谱（可运行完整项目）

一个**真实可运行**的 K8s 组件关系知识图谱系统：后端提供 REST API，数据持久化在 SQLite 文件库中，
前端所有内容由接口返回，支持组件的增删改查、知识条目与排障 SOP 的状态流转、审计日志、导入导出。

> 本项目不是 UI 原型，也不是写死数据的静态页。页面上的每一个节点、每一条连线、每一段知识正文都来自数据库；
> 新建 / 编辑 / 删除都会真实写入 `backend/data/atlas.db`，并在 `audit_log` 表留下记录。

---

## 1. 技术选型与理由

| 层 | 选型 | 理由 |
|---|---|---|
| 后端框架 | **FastAPI** | 自带 OpenAPI 文档（`/docs`），Pydantic 做请求校验，写 CRUD 最快 |
| 数据访问 | **SQLAlchemy 2.0 ORM** | 模型即表结构，改字段只改一处；后续换 PostgreSQL 只改 `DATABASE_URL` |
| 存储 | **SQLite（文件）** | 零安装、零配置，文件即数据库，满足"持久化"要求；ORM 层已隔离，可平滑迁 PG |
| 校验 | **Pydantic v2** | 入参强校验，非法请求直接 422，避免脏数据入库 |
| 服务 | **Uvicorn** | ASGI 服务器，单进程即可跑 |
| 前端 | **原生 HTML/CSS/JS** | 零构建步骤，后端同源托管即可打开；不引入 npm 构建链 |
| 端到端测试 | **Python 脚本 + stdlib** | 不依赖 pytest 也能跑，输出 PASS/FAIL 清单 |

**为什么不用 npm 前端框架**：本项目后端复杂度占比更高，引入 Vite/React 会多出一条构建链，
对"能本地跑起来"是负收益。前端已按"数据/渲染/交互"分层，后续迁框架成本可控。

---

## 2. 工程结构

```
k8s-panorama/
├── README.md                  ← 本文档（开发文档 + 任务清单 + 测试方式）
├── requirements.txt           ← 依赖清单
├── backend/
│   ├── run.py                 ← 启动入口（python run.py）
│   ├── data/
│   │   └── atlas.db           ← SQLite 数据库文件（首次启动自动生成并灌入种子数据）
│   └── app/
│       ├── __init__.py
│       ├── config.py          ← 配置：数据库路径、端口、CORS
│       ├── db.py              ← engine / SessionLocal / Base / get_db 依赖
│       ├── models.py          ← 10 张表的 ORM 模型
│       ├── schemas.py         ← Pydantic 入参/出参模型
│       ├── crud.py            ← 全部数据库读写逻辑（唯一写库入口，自动写审计）
│       ├── seed.py            ← 种子数据：41 组件 / 42 关系 / 8 分组 / 知识 / SOP / YAML
│       └── routers/
│           ├── __init__.py
│           ├── atlas.py       ← 图谱聚合、搜索、视图、健康检查
│           ├── groups.py      ← 分组 CRUD
│           ├── nodes.py       ← 组件 CRUD
│           ├── edges.py       ← 关系 CRUD
│           ├── layers.py      ← 图层/分类
│           ├── notes.py       ← 知识条目 CRUD + 状态流转
│           ├── sops.py        ← 排障 SOP CRUD + 状态流转
│           ├── yamls.py       ← YAML 片段 CRUD
│           ├── audit.py       ← 审计日志查询
│           └── io.py          ← 导出 / 导入（真实文件 IO）
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── app.js                 ← 全部数据来自 fetch，无写死内容
├── scripts/
│   ├── test_api.py            ← 端到端接口测试（逐条打印 PASS/FAIL）
│   └── reset_db.py            ← 删库重建 + 重灌种子数据
└── tests/
    └── manual_steps.md        ← 手工验收步骤
```

---

## 3. 数据模型（10 张表）

| 表 | 作用 | 关键字段 |
|---|---|---|
| `layer` | 分类/图层（8 项） | `id` `label` `color` `show_in_legend` `show_in_filter` `sort_order` |
| `atlas_group` | 分组容器（8 个，编号①~⑨，跳过⑥） | `id` `ordinal` `title` `subtitle` `x` `y` `w` `h` `sort_order` |
| `node` | 组件节点（41 个） | `id` `group_id` `layer_id` `name` `kind` `summary` `cmd` `x` `y` `created_at` `updated_at` |
| `node_field` | 组件的关键字段（1 对多） | `id` `node_id` `label` `value` `sort_order` |
| `edge` | 组件关系（42 条） | `id` `from_node` `to_node` `label` `layer_id` `sort_order` |
| `note` | 知识条目（含状态流转） | `slug` `node_id` `title` `markdown` `status` `updated_at` |
| `sop` | 排障 SOP（含状态流转） | `symptom` `title` `status` `updated_at` |
| `sop_step` | SOP 步骤（1 对多） | `id` `sop_id` `step_no` `action` `expect` `command` |
| `yaml_snippet` | YAML 片段 | `id` `node_id` `title` `yaml` |
| `audit_log` | 审计日志（每次写操作） | `id` `action` `entity` `entity_id` `detail` `created_at` |

**状态流转**（真实可验证）：

```
note / sop:  draft ──publish──> review ──approve──> published
                 └──────────── archive ────────────┘   （任意状态 → archived）
              archived ──restore──> draft
```

---

## 4. 任务清单（实现进度）

### 后端
- [x] T1 配置与数据库引擎（`config.py` / `db.py`）
- [x] T2 ORM 模型（`models.py`，10 张表）
- [x] T3 请求/响应 Schema（`schemas.py`）
- [x] T4 CRUD 层（`crud.py`，唯一写库入口 + 自动写审计）
- [x] T5 种子数据（`seed.py`，41 组件 / 42 关系 / 8 分组 / 知识 / SOP / YAML）
- [x] T6 图谱路由（`atlas.py`：聚合、搜索、视图、健康检查）
- [x] T7 分组 / 组件 / 关系 / 图层 CRUD 路由
- [x] T8 知识条目 + SOP + YAML 路由（含状态流转）
- [x] T9 审计日志 + 导入导出路由
- [x] T10 主入口（`main.py`：CORS、路由注册、同源托管前端、启动即建表+灌种子）

### 前端
- [x] T11 页面骨架 `index.html` + 样式 `styles.css`
- [x] T12 `app.js`：全部数据走 fetch，组件/关系/知识的新增·编辑·删除表单，状态流转按钮

### 测试与交付
- [x] T13 端到端测试脚本 `scripts/test_api.py`
- [x] T14 实际启动服务跑通全部接口（验证证据见第 9 节）
- [x] T15 手工验收步骤文档 `tests/manual_steps.md`

---

## 5. 依赖清单

`requirements.txt`：

```
fastapi>=0.110
uvicorn>=0.27
sqlalchemy>=2.0
pydantic>=2.5
```

无其他依赖。前端零依赖、零构建。

---

## 6. 安装与启动

### 6.1 安装依赖

```bash
cd k8s-panorama
python -m pip install -r requirements.txt
```

> Windows 若 `python` 指向不明版本，用 `py -3 -m pip install -r requirements.txt`。

### 6.2 启动后端

```bash
cd k8s-panorama/backend
python run.py
```

默认监听 `http://127.0.0.1:8000`。首次启动自动：
1. 创建 `backend/data/atlas.db`
2. 建 10 张表
3. 灌入种子数据（41 组件 / 42 关系 / 8 分组 / 知识 / SOP / YAML）

等价命令：`python -m uvicorn app.main:app --reload --port 8000`

### 6.3 打开前端

**方式 A（推荐，同源无跨域）**：后端已托管前端，直接访问

```
http://127.0.0.1:8000/
```

**方式 B（静态服务）**：

```bash
cd k8s-panorama/frontend
python -m http.server 5173
# 浏览器打开 http://127.0.0.1:5173/
```

此方式需要后端已启动，`config.py` 的 `CORS_ORIGINS` 默认已包含该源。

### 6.4 环境变量配置

| 变量 | 默认值 | 说明 |
|---|---|---|
| `ATLAS_DB` | `backend/data/atlas.db` | SQLite 文件路径 |
| `ATLAS_PORT` | `8000` | 监听端口 |
| `ATLAS_HOST` | `127.0.0.1` | 监听地址 |
| `ATLAS_CORS` | `http://127.0.0.1:5173,http://localhost:5173` | 允许的跨域源，逗号分隔 |
| `ATLAS_SEED` | `1` | 设为 `0` 则启动时不灌种子数据 |

示例：

```bash
# bash
ATLAS_PORT=9000 python run.py
# PowerShell
$env:ATLAS_PORT="9000"; python run.py
```

### 6.5 重置数据库

```bash
python scripts/reset_db.py
```

删除 `backend/data/atlas.db` 后重建并重新灌种子数据。

---

## 7. API 清单

所有接口前缀 `/api`，出错返回 `{"detail": "..."}`。交互式文档：<http://127.0.0.1:8000/docs>

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查，返回库内计数 |
| GET | `/api/atlas/graph` | 一次返回分组 + 节点 + 边 + 图层（前端首屏用） |
| GET | `/api/atlas/search?q=关键词&limit=20` | 跨组件 / 知识 / SOP 检索 |
| GET | `/api/atlas/views` | 视图定义 |
| GET/POST/PATCH/DELETE | `/api/groups[/{id}]` | 分组增删改查 |
| GET/POST/PATCH/DELETE | `/api/nodes[/{id}]` | 组件增删改查（含 fields） |
| GET/POST/PATCH/DELETE | `/api/edges[/{id}]` | 关系增删改查 |
| GET/PATCH | `/api/layers[/{id}]` | 图层列表 / 改颜色与显隐 |
| GET/POST/PATCH/DELETE | `/api/notes[/{slug}]` | 知识条目 CRUD |
| POST | `/api/notes/{slug}/transition` | **状态流转**：publish / approve / archive / restore |
| GET/POST/PATCH/DELETE | `/api/sops[/{symptom}]` | 排障 SOP CRUD |
| POST | `/api/sops/{symptom}/transition` | **状态流转** |
| GET/POST/PATCH/DELETE | `/api/yamls[/{id}]` | YAML 片段 CRUD |
| GET | `/api/audit?limit=50&entity=` | 审计日志（每次写操作留痕） |
| GET | `/api/io/export` | 导出全库为 JSON |
| POST | `/api/io/import?mode=replace\|merge` | 导入 JSON 到库（真实写库） |

---

## 8. 测试方式

### 8.1 一键端到端测试（推荐）

```bash
# 服务已在 8000 端口运行的前提下
python scripts/test_api.py
```

脚本依次验证并打印 `PASS/FAIL`：健康检查 → 图谱聚合 → 组件 CRUD → 关系 CRUD →
分组 CRUD → 搜索 → 知识条目状态流转 → SOP 状态流转 → YAML CRUD → 审计日志 → 导出导入 →
最后清理自己造的测试数据。

### 8.2 手工 curl 示例

```bash
# 健康检查
curl http://127.0.0.1:8000/api/health

# 建一个组件（真实写库）
curl -X POST http://127.0.0.1:8000/api/nodes \
  -H "Content-Type: application/json" \
  -d '{"id":"test-node","group_id":"g3","layer_id":"policy","name":"测试组件",
       "kind":"测试类型","summary":"这是一个新建的组件","cmd":"kubectl get pods",
       "x":120,"y":700,"fields":[{"label":"字段","value":"值"}]}'

# 改它
curl -X PATCH http://127.0.0.1:8000/api/nodes/test-node \
  -H "Content-Type: application/json" -d '{"summary":"改过了"}'

# 删它
curl -X DELETE http://127.0.0.1:8000/api/nodes/test-node

# 看审计日志（上面三步都会留痕）
curl "http://127.0.0.1:8000/api/audit?limit=5"
```

### 8.3 浏览器验收步骤

见 `tests/manual_steps.md`，逐条列出"点哪里 → 应该看到什么 → 数据库里应该多出什么"。

---

## 9. 验证证据

启动服务后执行 `python scripts/test_api.py` 的完整输出（2026-09-25 实测）：

```text
== K8s Panorama 端到端测试 ==  http://127.0.0.1:8000/api

PASS  健康检查返回 200   {'status': 'ok', 'database': 'sqlite', 'counts': {'layers': 8, 'groups': 8, 'nodes': 41, 'fields': 41, 'edges': 42, 'notes': 3, 'sops': 2, 'sop_steps': 8, 'yamls': 2, 'audit': 90}}
PASS  图谱聚合返回 200
PASS  图层 8 个   实际 8
PASS  分组 8 个   实际 8
PASS  组件 41 个   实际 41
PASS  关系 42 条   实际 42
PASS  组件带关键字段
PASS  POST 组件 返回 201   201
PASS  POST 组件 内容一致
PASS  GET 组件详情
PASS  组件字段落库
PASS  PATCH 组件
PASS  PATCH 覆盖字段
PASS  POST 关系   201
PASS  GET 关系详情
PASS  PATCH 关系
PASS  搜索命中组件   命中 1
PASS  搜索命中新建组件
PASS  中文搜索不报错
PASS  POST 分组   201
PASS  PATCH 分组
PASS  DELETE 分组(force)   {'deleted': 1, 'id': 'zz-test-group', 'moved_nodes': 0}
PASS  POST 知识条目   201
PASS  知识条目初始状态 draft
PASS  流转 publish: draft→review   review
PASS  流转 approve: review→published   published
PASS  非法流转被拒（published 不能 publish）   返回 400
PASS  流转 archive
PASS  流转 restore: archived→draft
PASS  DELETE 知识条目
PASS  POST 排障 SOP   201
PASS  SOP 步骤落库
PASS  SOP 流转 publish
PASS  SOP 流转 approve
PASS  DELETE 排障 SOP
PASS  POST YAML   201
PASS  PATCH YAML
PASS  DELETE YAML
PASS  审计日志返回 200
PASS  审计含 create
PASS  审计含 update
PASS  审计含 delete
PASS  审计含 transition
PASS  审计含 import 或 seed
PASS  导出全库   导出节点 42
PASS  导出含知识/SOP/YAML
PASS  导入(merge) 回灌自身   {'layers': 8, 'groups': 8, 'nodes': 42, 'edges': 43, 'notes': 3, 'sops': 2, 'yamls': 2}
PASS  清理：删除测试组件
PASS  清理后组件数回到 41   实际 41
PASS  清理后关系数回到 42   实际 42

============================================================
PASS 50   FAIL 0
============================================================
```

---

## 10. 已知限制

1. **SQLite 单文件**：并发写入能力有限，单用户/小团队场景足够；如需多写并发，改 `config.DATABASE_URL` 为 PostgreSQL 连接串即可（ORM 层无需改动）。
2. **无鉴权**：这是个人或小团队内部工具，接口未做登录。若要放到公网，必须在网关层加认证，并在写操作前加权限校验。
3. **不接 K8s 集群**：本项目是"知识图谱 + 知识库"，不会去连你的真实集群。右侧的验证命令是给人复制到自己终端执行的，后端**不执行任何 shell 命令**（安全红线）。
4. 种子数据中的知识条目、排障 SOP、YAML 片段为示例内容，可在界面上直接编辑替换。
