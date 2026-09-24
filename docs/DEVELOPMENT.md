# 开发说明

面向要修改或扩展本项目的开发者。产品说明见 [`../README.md`](../README.md)，部署见 [`../deploy/README.md`](../deploy/README.md)。

---

## 1. 分层与职责

```
请求 → routers/*.py（参数校验 + 调 crud）
          ↓
      crud.py（唯一写库入口，自动写审计）
          ↓
      models.py（ORM 表结构）
          ↓
      db.py（engine / SessionLocal / get_db）
```

| 文件 | 职责 | 修改时要注意 |
|---|---|---|
| `app/config.py` | 全部可调项（DB 路径、端口、CORS、静态目录） | 新增配置项必须给默认值，保证零配置可跑 |
| `app/db.py` | engine、SessionLocal、`get_db` 依赖 | SQLite 的 `check_same_thread` 与 `foreign_keys` PRAGMA 已处理，勿删 |
| `app/models.py` | 10 张表的 ORM 定义 | 改字段后需 `python scripts/reset_db.py` 重建（开发期） |
| `app/schemas.py` | Pydantic 入参/出参 | `*In` 新建、`*Patch` 局部更新、`*Out` 出参，命名别混 |
| `app/crud.py` | 全部数据库读写 | **唯一允许写库的地方**，每个写操作必须配一条 `audit()` |
| `app/seed.py` | 首次启动的种子数据 | 由 `scripts/_gen_seed.py` 生成，勿手工改数据部分 |
| `app/routers/*.py` | HTTP 接口 | 只做校验与编排，不直接写 SQL |
| `app/main.py` | 应用装配：CORS、路由注册、静态托管、启动钩子 | 静态挂载 `app.mount("/")` 必须在路由注册之后 |
| `frontend/app.js` | 全部前端逻辑 | 数据一律来自 `api()`，禁止把图谱内容写死在前端 |

## 2. 数据流

**一次点击的完整链路**

```
用户点击节点卡片
  → select(id)
      → 更新 S.sel（唯一状态源）
      → 画布：命中卡片加 .sel，drawEdges() 重画连线（命中边加粗，无关边压暗）
      → 右栏：renderInspector(id) 重新渲染
          → 关键属性 / 基础信息来自 /api/atlas/graph 已取回的数据
          → 「相关知识条目」额外请求 /api/notes?node_id=<id>
          → 「上下游」由本地 edges 反查得到
      → 状态栏文案更新
```

**一次写操作**

```
表单提交 → api("POST"|"PATCH"|"DELETE", ...)
  → 路由层校验（Pydantic，非法直接 422）
  → crud 层写库 + audit() 记录
  → 返回最新对象 → 前端 reloadGraph() 或 refreshPanel()
  → 页底「最近变更」表格可见该条审计
```

## 3. 常见扩展怎么做

### 3.1 新增一个组件

改数据库即可，**不用改代码**：

```bash
curl -X POST http://127.0.0.1:8000/api/nodes \
  -H "Content-Type: application/json" \
  -d '{"id":"my-component","group_id":"g3","layer_id":"policy","name":"我的组件",
       "kind":"自定义","summary":"一句话说明","cmd":"kubectl get foo",
       "x":1240,"y":560,"fields":[{"label":"端口","value":"8443"}]}'
```

或者在界面上点「+ 新建组件」。若希望它成为默认数据的一部分，编辑 `backend/app/seed.py`
（数据部分可由 `scripts/_gen_seed.py` 重新生成）。

### 3.2 新增一种分类（图层）

```sql
INSERT INTO layer (id, label, color, show_in_legend, show_in_filter, sort_order)
VALUES ('mesh', '服务网格', '#22D3EE', 1, 1, 9);
```

图例、左栏过滤器、连线配色三处会自动生效，无需改前端。

### 3.3 新增一个状态流转

改 `crud.py` 的 `STATUS_FLOW`：

```python
STATUS_FLOW = {
    "publish": ("draft", "review"),
    "approve": ("review", "published"),
    "archive": (None, "archived"),
    "restore": ("archived", "draft"),
    "reject":  ("review", "draft"),        # 新增示例
}
```

`schemas.py` 的 `TransitionIn.action` 是 `Literal[...]`，需要同步加上新动作，
否则请求会被 Pydantic 拦成 422。

### 3.4 新增一个一级页签

1. `frontend/app.js` 的 `TABS` 数组加一项
2. `switchTab()` 里加对应分支，并在 `renderPanel()` 里加渲染函数
3. 若需要后端数据，在 `routers/` 加路由并在 `main.py` 注册

### 3.5 换数据库

`app/config.py` 的 `DATABASE_URL` 改成 PostgreSQL 连接串：

```python
DATABASE_URL = os.getenv("ATLAS_DB_URL", "postgresql+psycopg://user:pass@host/atlas")
```

ORM 层无需改动（未使用 SQLite 专有语法）。需额外安装 `psycopg`。

## 4. 代码约定

1. **禁止在 `routers/` 里直接操作 Session 写库**，一律走 `crud.py`。
2. **每个写操作必须调用 `audit()`**，否则「最近变更」会漏记录，验收会失败。
3. **前端禁止 `innerHTML` 拼接用户输入**，一律 `textContent` 或先 `esc()` 转义。
4. **后端不执行任何 shell 命令**。界面上的 `kubectl` 命令只是文本。
5. 新增环境变量必须在 `config.py` 给默认值，并在 `README.md` 的配置表登记。
6. 改完后端代码**必须重启服务**（未加 `--reload` 时改动不生效）。

## 5. 本地开发

```bash
# 后端（自动重载模式）
cd backend
python -m uvicorn app.main:app --reload --port 8000

# 前端：改 frontend/ 下文件后刷新浏览器即可，无构建步骤
# 若要单独起前端调试服务（会跨域，CORS 默认已放行 5173）
cd frontend && python -m http.server 5173
```

### 重建数据库（开发期常用）

```bash
python scripts/reset_db.py          # 删库 + 建表 + 灌种子
ATLAS_SEED=0 python run.py          # 只建空表，不灌种子
```

### 样式调整

前端排版令牌集中在 `frontend/styles.css` 的 `:root`：
字号阶梯 `--fs-*`、行高 `--lh-*`、字距 `--ls-*`、文字对比度 `--t1` ~ `--t4`。
改这里即可全局生效，不要在组件里写死字号。
