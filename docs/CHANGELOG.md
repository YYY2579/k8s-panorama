# 变更记录与验收证据

---

## [1.2.0] — 2026-09-26

对应路线图 M2「连得上 + 看得见」：K8s 集群只读接入 + 资源可视化 + 三种数据源切换。

### 新增

**M2a 集群只读探针**（`backend/app/cluster/` 独立子包）

- `client.py`：白名单只读客户端，对外只有 `get()`，代码里不存在 post/put/patch/delete
- `mapper.py`：K8s 对象 → 图谱组件 ID 的纯函数汇总（Node Ready 比例、Pod 阶段、
  工作负载期望 vs 就绪、CNI 探测、日志 agent 探测、PSA 级别…）
- `cache.py`：TTL 内存缓存 + 同 key 并发去重；另有「上一次成功快照」供降级时使用
- `snapshot.py`：并发采集 24 条 API 路径；单条失败只影响对应组件，
  **全部失败**才判定集群不可达
- 路由挂在 `/api/cluster/*`，与 `/api/atlas/*` 物理分离（互不 import）
- 不可达 → 503 + `{"degraded": true, "reason": ...}`；有上次快照则返回并标 `stale`
- 凭证：`ATLAS_K8S_API` + `ATLAS_K8S_TOKEN`，或读 kubeconfig；Pod 内可走 ServiceAccount

**M2b 资源可视化 + 三数据源**

- 顶栏数据源切换：**知识库**（`/api/atlas/graph`）/ **官方全景**（`/api/atlas/official`，
  来自种子数据不受编辑影响）/ **集群实况**
- 集群视图**复用全景图槽位坐标**（布局是心智锚点），按四态填充：
  在位 / 异常（琥珀脉冲）/ 未检测到（置灰虚线）/ 采集不到（半透明）
- 概念连线 + 集群状态联动：任一端异常 → 转琥珀加粗
- 右栏「集群实况」卡片 + 「常用命令」面板：命令按实况**参数化**（填入真实对象名），
  异常时 describe/logs 类定位命令置顶，写操作命令加「写」标记
- 顶栏集群徽标：已连接 / N 项异常 / 未连接

**配套**

- `scripts/mock_k8s.py`：模拟 kube-apiserver，返回真实结构 JSON，
  刻意制造 NotReady 节点、Pending Pod、CrashLoopBackOff、Gateway API 404
- README 新增「接入自己的 K8s 集群」：两种凭证方式、最小 RBAC、无集群时用模拟器

### 验收证据

| 测试 | 结果 |
|---|---|
| `pytest backend/tests` | **99 passed / 0 failed**（新增 26 个集群用例） |
| `scripts/test_api.py` | **51 PASS / 0 FAIL** |
| 前端三数据源 + 集群视图注入测试 | **25 PASS / 0 FAIL** |

集群用例覆盖：mapper 纯函数、client 只读边界（无写方法、404 → ResourceNotFound、
不可达 → ClusterUnreachable）、快照四态、单组件失败不扩散、路由 503 降级、
stale 快照、以及「集群接口不写任何 atlas 数据」。

### 开发中修掉的问题

| 问题 | 根因 |
|---|---|
| 集群完全不可达时接口返回 200 而非 503 | `collect()` 把单条路径失败吞成 error 字段，整体不可达也不抛异常；改为「全部路径失败才抛 ClusterUnreachable」 |
| `from .cluster import router` 拿到子模块而非 APIRouter | 包内模块名与实例名冲突；改 `from .cluster.router import router` |
| `summarize_ingresses` 崩溃 | 集合推导里放的是 rule dict 而非 host 字符串（unhashable type: dict） |
| 对外状态出现 `not_found` | 内部状态与约定四态不一致；`_c()` 里统一归一成 `not_detected` |
| 旧服务未重启导致验证结论偏差 | 改完 `_c()` 后忘记重启，前端看到还是旧行为 |

---

## [1.2.0] — 2026-09-26

对应路线图 M2「连得上 + 看得见」：K8s 集群只读接入 + 资源可视化 + 三种数据源切换。

### 新增

**M2a 集群只读探针**（`backend/app/cluster/` 独立子包）

- `client.py`：白名单只读客户端，对外只有 `get()`，代码里不存在 post/put/patch/delete
- `mapper.py`：K8s 对象 → 图谱组件 ID 的纯函数汇总（Node Ready 比例、Pod 阶段、
  工作负载期望 vs 就绪、CNI 探测、日志 agent 探测、PSA 级别…）
- `cache.py`：TTL 内存缓存 + 同 key 并发去重；另有「上一次成功快照」供降级时使用
- `snapshot.py`：并发采集 24 条 API 路径；单条失败只影响对应组件，
  **全部失败**才判定集群不可达
- 路由挂在 `/api/cluster/*`，与 `/api/atlas/*` 物理分离（互不 import）
- 不可达 → 503 + `{"degraded": true, "reason": ...}`；有上次快照则返回并标 `stale`
- 凭证：`ATLAS_K8S_API` + `ATLAS_K8S_TOKEN`，或读 kubeconfig；Pod 内可走 ServiceAccount

**M2b 资源可视化 + 三数据源**

- 顶栏数据源切换：**知识库**（`/api/atlas/graph`）/ **官方全景**（`/api/atlas/official`，
  来自种子数据不受编辑影响）/ **集群实况**
- 集群视图**复用全景图槽位坐标**（布局是心智锚点），按四态填充：
  在位 / 异常（琥珀脉冲）/ 未检测到（置灰虚线）/ 采集不到（半透明）
- 概念连线 + 集群状态联动：任一端异常 → 转琥珀加粗
- 右栏「集群实况」卡片 + 「常用命令」面板：命令按实况**参数化**（填入真实对象名），
  异常时 describe/logs 类定位命令置顶，写操作命令加「写」标记
- 顶栏集群徽标：已连接 / N 项异常 / 未连接

**配套**

- `scripts/mock_k8s.py`：模拟 kube-apiserver，返回真实结构 JSON，
  刻意制造 NotReady 节点、Pending Pod、CrashLoopBackOff、Gateway API 404
- README 新增「接入自己的 K8s 集群」：两种凭证方式、最小 RBAC、无集群时用模拟器

### 验收证据

| 测试 | 结果 |
|---|---|
| `pytest backend/tests` | **99 passed / 0 failed**（新增 26 个集群用例） |
| `scripts/test_api.py` | **51 PASS / 0 FAIL** |
| 前端三数据源 + 集群视图注入测试 | **25 PASS / 0 FAIL** |

集群用例覆盖：mapper 纯函数、client 只读边界（无写方法、404 → ResourceNotFound、
不可达 → ClusterUnreachable）、快照四态、单组件失败不扩散、路由 503 降级、
stale 快照、以及「集群接口不写任何 atlas 数据」。

### 开发中修掉的问题

| 问题 | 根因 |
|---|---|
| 集群完全不可达时接口返回 200 而非 503 | `collect()` 把单条路径失败吞成 error 字段，整体不可达也不抛异常；改为「全部路径失败才抛 ClusterUnreachable」 |
| `from .cluster import router` 拿到子模块而非 APIRouter | 包内模块名与实例名冲突；改 `from .cluster.router import router` |
| `summarize_ingresses` 崩溃 | 集合推导里放的是 rule dict 而非 host 字符串（unhashable type: dict） |
| 对外状态出现 `not_found` | 内部状态与约定四态不一致；`_c()` 里统一归一成 `not_detected` |
| 旧服务未重启导致验证结论偏差 | 改完 `_c()` 后忘记重启，前端看到还是旧行为 |

---

## [1.1.0] — 2026-09-26

对应路线图 M1「可信」：鉴权与权限、CI 与单元测试、数据库迁移。**纯增量，未改动既有业务逻辑。**

### 新增

**M1a 鉴权与权限**

- `user` 表：用户名、口令哈希、角色（`admin` / `viewer`）、启用状态、最近登录时间
- 口令哈希：标准库 `hashlib.pbkdf2_hmac`（SHA-256 / 26 万次迭代 / 128 位随机盐），
  格式自带算法与参数，常量时间比较；未引入 passlib/bcrypt，避免平台编译依赖
- 会话：`itsdangerous` 签名 cookie（HttpOnly + SameSite=Lax），payload 只有 uid 与 role，
  另按 payload 内的 `iat` 做二次过期校验
- 依赖：`current_user`（401）、`require_admin`（403）、`crud.set_actor()`（记录操作者）
- 22 个写接口全部要求 admin；读接口保持公开
- 审计日志新增 `actor` 字段，支持按实体 / 操作者过滤
- 首启引导：无用户时创建管理员。口令取 `ATLAS_ADMIN_PASSWORD`，未设置则随机生成并只打印一次
- 前端：独立登录页 `/login.html`、顶栏登录态芯片、未登录隐藏写入口、401/403 友好提示
- 自我保护：不能降级、停用或删除当前登录的自己

**M1b 测试与 CI**

- `backend/tests/`：73 个 pytest 用例（口令哈希、会话签名与篡改检测、角色拦截、
  CRUD、状态流转、导入导出事务回滚）
- `.github/workflows/ci.yml`：安装依赖 → pytest → 启动后端 → 端到端测试
- `scripts/test_api.py` 适配鉴权：用 CookieJar 自动带会话，运行前需设置 `ATLAS_ADMIN_PASSWORD`

**M1c 数据库迁移**

- Alembic 接入，初始迁移 `d616d19e93cb` 建 11 张业务表
- 服务启动走 `upgrade head`，取代 `create_all`
- `ensure_migration_state()`：识别"迁移上线前的旧库"并 `stamp head`，避免重复建表
- `scripts/reset_db.py` 改为「drop_all → upgrade head → 灌种子」

### 验收证据

| 测试 | 结果 |
|---|---|
| `pytest backend/tests` | **73 passed / 0 failed** |
| `scripts/test_api.py` | **51 PASS / 0 FAIL** |
| 前端未登录态注入测试 | **7 PASS / 0 FAIL** |
| 前端 admin 闭环注入测试 | **12 PASS / 0 FAIL** |

前端闭环覆盖：登录 → 写按钮出现 → 建组件 → 改 → 删 → 404 → 审计 3 条且 actor 均为 admin。

### 开发中修掉的问题

| 问题 | 根因 |
|---|---|
| 所有写接口 500 | `deps.py` 里 `from .. import crud` 超出顶级包，改为 `from . import crud` |
| 审计 actor 全是 anonymous | ContextVar 无法跨 FastAPI 的同步依赖与路由函数体传递；改为在路由函数体内调 `crud.set_actor()` |
| `/api/audit` 500 | 模型加了 `actor` 列但旧表没有，`create_all` 不补列；先加 `ensure_schema()` 兜底，最终由 Alembic 取代 |
| `/api/audit?actor=` 过滤无效 | `crud.list_audit` 加了参数但路由没暴露 |
| 37 个 pytest 失败 | 某个测试执行登出，把 session 级共享 client 的 cookie 清掉；fixture 改 function 作用域 |

---

## [1.1.0] — 2026-09-26

对应路线图 M1「可信」：鉴权与权限、CI 与单元测试、数据库迁移。**纯增量，未改动既有业务逻辑。**

### 新增

**M1a 鉴权与权限**

- `user` 表：用户名、口令哈希、角色（`admin` / `viewer`）、启用状态、最近登录时间
- 口令哈希：标准库 `hashlib.pbkdf2_hmac`（SHA-256 / 26 万次迭代 / 128 位随机盐），
  格式自带算法与参数，常量时间比较；未引入 passlib/bcrypt，避免平台编译依赖
- 会话：`itsdangerous` 签名 cookie（HttpOnly + SameSite=Lax），payload 只有 uid 与 role，
  另按 payload 内的 `iat` 做二次过期校验
- 依赖：`current_user`（401）、`require_admin`（403）、`crud.set_actor()`（记录操作者）
- 22 个写接口全部要求 admin；读接口保持公开
- 审计日志新增 `actor` 字段，支持按实体 / 操作者过滤
- 首启引导：无用户时创建管理员。口令取 `ATLAS_ADMIN_PASSWORD`，未设置则随机生成并只打印一次
- 前端：独立登录页 `/login.html`、顶栏登录态芯片、未登录隐藏写入口、401/403 友好提示
- 自我保护：不能降级、停用或删除当前登录的自己

**M1b 测试与 CI**

- `backend/tests/`：73 个 pytest 用例（口令哈希、会话签名与篡改检测、角色拦截、
  CRUD、状态流转、导入导出事务回滚）
- `.github/workflows/ci.yml`：安装依赖 → pytest → 启动后端 → 端到端测试
- `scripts/test_api.py` 适配鉴权：用 CookieJar 自动带会话，运行前需设置 `ATLAS_ADMIN_PASSWORD`

**M1c 数据库迁移**

- Alembic 接入，初始迁移 `d616d19e93cb` 建 11 张业务表
- 服务启动走 `upgrade head`，取代 `create_all`
- `ensure_migration_state()`：识别"迁移上线前的旧库"并 `stamp head`，避免重复建表
- `scripts/reset_db.py` 改为「drop_all → upgrade head → 灌种子」

### 验收证据

| 测试 | 结果 |
|---|---|
| `pytest backend/tests` | **73 passed / 0 failed** |
| `scripts/test_api.py` | **51 PASS / 0 FAIL** |
| 前端未登录态注入测试 | **7 PASS / 0 FAIL** |
| 前端 admin 闭环注入测试 | **12 PASS / 0 FAIL** |

前端闭环覆盖：登录 → 写按钮出现 → 建组件 → 改 → 删 → 404 → 审计 3 条且 actor 均为 admin。

### 开发中修掉的问题

| 问题 | 根因 |
|---|---|
| 所有写接口 500 | `deps.py` 里 `from .. import crud` 超出顶级包，改为 `from . import crud` |
| 审计 actor 全是 anonymous | ContextVar 无法跨 FastAPI 的同步依赖与路由函数体传递；改为在路由函数体内调 `crud.set_actor()` |
| `/api/audit` 500 | 模型加了 `actor` 列但旧表没有，`create_all` 不补列；先加 `ensure_schema()` 兜底，最终由 Alembic 取代 |
| `/api/audit?actor=` 过滤无效 | `crud.list_audit` 加了参数但路由没暴露 |
| 37 个 pytest 失败 | 某个测试执行登出，把 session 级共享 client 的 cookie 清掉；fixture 改 function 作用域 |

---

## [1.0.1] — 2026-09-26

依据 [`audits/code-review-2026-09-26.md`](audits/code-review-2026-09-26.md) 的 15 项发现全面修复。
**未新增范围外功能**，仅修正缺陷与规范问题。

### 修复

**功能性缺陷**

- **A1** 详情面板异步竞态：`renderInspector` 中途 `await /notes` 后不再校验是否已过期，
  快速切换节点时旧节点的「相关知识条目」会追加到新节点面板。改为渲染令牌对账。
- **A2** 测试脚本在服务未启动时崩溃：`req()` 只捕 `HTTPError` 不捕 `URLError`，
  而 `cleanup_leftovers()` 排在健康检查之前。改为两者都捕获，连接失败返回 0 由调用方判失败。
- **A3** `delete_node` 冗余置空：模型外键已声明 `ondelete="SET NULL"` 且已开启
  `PRAGMA foreign_keys=ON`，手工 `UPDATE` 既重复又绕过 ORM 缓存。已删除，依赖外键自动处理。
- **A4** `import` 的 replace 模式无事务保护：清空后立即 `commit`，导入失败会丢数据。
  改为清空与导入同一事务，任一步失败整体回滚，并以 400 返回具体原因。
- **A5** 导入接口无结构校验：`payload: dict` 接受任意 JSON。新增 `schemas.ImportPayload`，
  列表字段非数组直接 422。

**健壮性与安全性**

- **B1** `drawEdges` 对 `nodeById()` 未判空：边引用缺失节点时整片连线消失。改为先取节点判空再用，
  同时消除了一条边内三次重复查询。
- **B2** `api()` 无超时：后端卡住时前端永久无反馈。加 `AbortController` + 15s 超时与明确错误。
- **B3** `syncLayers` 用 `indexOf` 反查图层：正确性依赖隐式的 DOM 顺序，左栏结构一变就错位。
  改为 `forEach` 下标 + 过滤后数组。

**性能**

- **C1** `drawEdges` 每次 hover / 缩放 / 平移全量重建约 210 个 SVG 节点。
  全部 8 个调用点改走 `scheduleDrawEdges()` 合帧，并加 `setTimeout` 兜底
  （无头渲染环境 rAF 不触发，没有兜底会画不出连线）。
- **C2** `import_all` 的 node / sop 分支在循环内逐行 `flush`。移到循环外，语句往返从 N 次降到 1 次。

**规范与可维护性**

- **D1** `@app.on_event("startup")` 已弃用，改用 `lifespan` 异步上下文管理器。
- **D2** `config.py` 在 import 时创建目录，拆出 `ensure_db_dir()` 由 `db.py` 在建 engine 前调用。
- **D3** datetime 混用 aware / naive，比较时会抛 `TypeError`。
  `models._now()` 与新增的 `crud._utcnow()` 统一返回 naive UTC。
- **D4** `delete_group(force=True)` 隐式把节点搬到"排序第一个的其它分组"，
  用户感知为节点消失。新增显式 `move_to` 参数，目标不存在返回 400 且分组与组件都不动，
  审计日志记录搬迁去向。
- **D5** 前端两种渲染范式混用、`esc()` 定义在使用点之后。`esc()` 前移至文件首部工具区
  （删除重复定义），并在文件头写明渲染范式约定。

### 验收证据

| 测试 | 结果 |
|---|---|
| `python scripts/test_api.py`（原有 50 项断言） | PASS 50 / FAIL 0 |
| 修复专项验证（A3/A4/A5/D3/D4，18 项断言） | PASS 18 / FAIL 0 |
| 前端注入测试（A1/B1/B2/C1/D5 + 首屏/搜索/图层/页签，12 项断言） | PASS 12 / FAIL 0 |

合计 80 项断言全部通过；回归后数据库计数回到 41 组件 / 42 关系，无残留测试数据。
详细逐项证据见审查报告末尾的「修复状态」章节。

---

## [1.0.0] — 2026-09-25

首个可用版本。Git 提交 `dc42ec8`，仓库 <https://github.com/YYY2579/k8s-panorama>。

### 新增

- **后端服务**：FastAPI + SQLAlchemy 2.0 + SQLite，10 张表
  （`layer` / `atlas_group` / `node` / `node_field` / `edge` / `note` / `sop` / `sop_step` / `yaml_snippet` / `audit_log`）
- **完整 CRUD**：组件、关系、分组、知识条目、排障 SOP、YAML 片段，全部落到 SQLite 文件库
- **状态流转**：知识条目与 SOP 支持 `draft → review → published`，任意状态可 `archive`，
  `archived` 可 `restore` 回 `draft`；非法流转返回 HTTP 400
- **审计日志**：所有写操作自动写入 `audit_log`，可通过 `/api/audit` 查询
- **检索**：跨组件 / 知识 / SOP 的关键词检索；「网络链路」页签基于 BFS 计算真实最短路径
- **导入导出**：`/api/io/export` 导出全库 JSON，`/api/io/import` 支持 `merge` / `replace` 回灌
- **前端**：零依赖单页应用，全部数据来自 `/api`，6 个页签均接真实数据
- **种子数据**：41 个组件、42 条关系、8 个分组、8 个分类，另有 3 条知识、2 条 SOP、2 条 YAML 示例
- **部署**：`deploy/` 下提供宿主机（systemd + nginx）与 Docker（Dockerfile + Compose）两套方案

### 修复（开发过程中发现并已修）

| 问题 | 现象 | 根因 |
|---|---|---|
| `main.py` 未导入 `Depends` / `Session` | 服务启动即 `NameError` | 新增健康检查路由时漏加 import |
| `frontend/app.js` 模板字符串结尾引号写错（2 处） | 页面 JS 语法错误 | 反引号误写为单引号 |
| 导出的 ISO 时间字符串无法回灌 | `/api/io/import` 返回 500 | SQLite `DateTime` 列只接受 `datetime` 对象，已加 `_coerce_row()` 还原 |
| `seed.py` 中 shell 转义无效 | `SyntaxWarning` | `grep -A5 'Taints\|Allocated'` 改为 `-E 'Taints\|Allocated'` |
| 测试脚本中断会留下脏数据 | 重跑时计数不符 | 增加 `cleanup_leftovers()` 前置清理 |

---

## 实现清单（历史记录）

以下为初版开发时的任务分解与完成情况，保留作为过程追溯。

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
- [x] T14 实际启动服务跑通全部接口
- [x] T15 手工验收步骤文档 `tests/manual_steps.md`

---

## 验收证据

### 端到端接口测试

命令：`python scripts/test_api.py`（服务运行于 `127.0.0.1:8000`）

结果：**50 项断言全部 PASS，0 FAIL**。脚本会自行创建并清理测试数据，可重复执行。

完整输出见 [acceptance-test-output.txt](./acceptance-test-output.txt)。

### 覆盖范围

| 类别 | 断言数 | 说明 |
|---|---|---|
| 健康检查与图谱聚合 | 7 | 含 41 组件 / 42 关系 / 8 分组 / 8 图层的数量校验 |
| 组件 CRUD | 7 | POST 201 → GET → PATCH → 字段整体替换 |
| 关系 CRUD | 3 | POST → GET → PATCH |
| 搜索 | 3 | 英文命中、中文命中、新建组件可被搜到 |
| 分组 CRUD | 3 | POST → PATCH → force 删除 |
| 知识条目与状态流转 | 9 | draft→review→published、非法流转 400、archive、restore |
| 排障 SOP 与状态流转 | 4 | 含步骤落库校验 |
| YAML | 3 | POST → PATCH → DELETE |
| 审计日志 | 5 | create / update / delete / transition / import 五类记录均在 |
| 导出导入 | 2 | 导出 42 节点、merge 回灌成功 |
| 清理 | 2 | 删除测试数据后计数回到 41 / 42 |

### 本机环境

- Windows 10/11，Python 3.13.15，Docker CLI 29.8.0（daemon 未运行，镜像未在本机构建）
- FastAPI 0.141.1 / SQLAlchemy 2.0.54
- 浏览器渲染经 Edge 无头截图确认：状态栏显示「已加载 41 个组件 / 42 条关系」，
  组件详情页的「相关知识条目」来自 `/api/notes?node_id=...` 的真实查询结果
