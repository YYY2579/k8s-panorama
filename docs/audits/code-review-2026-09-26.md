# 代码审查报告

- 审查对象：`k8s-panorama` 全部源码（后端 `backend/app/` + `backend/run.py`、前端 `frontend/`、脚本 `scripts/`）
- 审查范围：`dc42ec8..HEAD`（两个提交，共 4910 行代码）
- 审查维度：逻辑正确性、潜在缺陷、性能、代码规范、可读性、安全性、可维护性
- 约束：**只审查，不修改代码**。所有"修正参考"仅为建议写法。
- 规范依据：仓库内 `docs/DEVELOPMENT.md` 第 4 节「代码约定」+ README「已知限制」

问题按严重程度分四组，共 14 项。每项含：位置、原文、原因、修正参考、理由。

---

## A. 功能性缺陷（建议优先修）

### A1. 前端详情面板存在异步竞态，右栏会张冠李戴

**位置**：`frontend/app.js:341`、`410`

**原文**：
```js
function select(id, silent, centerIt) {
  ...
  drawEdges(); renderInspector(id);        // ← 341：同步调用 async 函数，不等待
  ...
}
async function renderInspector(id) {
  ...
  const notes = await api("/notes?node_id=" + encodeURIComponent(id));   // ← 410：中途让出
  if (notes.length) {
    el.appendChild(card("相关知识条目", ...));   // ← 回来时 el 可能已经是另一个节点的面板
  }
```

**原因**：`renderInspector` 是 async，内部 `await` 之后才追加「相关知识条目」卡片。
用户快速点 A 再点 B 时，A 的请求后返回，此时 `$("insp")` 已被 B 重绘，
A 的知识条目会被**追加到 B 的面板末尾**，出现"点的是 Pod，却看到 NetworkPolicy 的知识条目"。

**修正参考**：
```js
let inspToken = 0;                       // 模块级
async function renderInspector(id) {
  const my = ++inspToken;                // 本次渲染的令牌
  ...
  const notes = await api("/notes?node_id=" + encodeURIComponent(id));
  if (my !== inspToken) return;          // 已有更新的渲染，丢弃本次结果
  if (notes.length) { el.appendChild(...); }
}
```

**理由**：这是"点击后看到错误内容"类缺陷，直接违背验收红线（点一下必须有正确效果）。
用令牌（或 AbortController）做请求对消是标准解法，改动仅 3 行。

### A2. 测试脚本在服务未启动时会崩溃，而不是给出友好提示

**位置**：`scripts/test_api.py:21-36`、`61`、`64-69`

**原文**：
```python
def req(method, path, body=None):
    ...
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            ...
    except urllib.error.HTTPError as e:      # ← 只捕 HTTPError
        ...

def main():
    ...
    cleanup_leftovers()                      # ← 61：在下面的 try 之前，未受保护
    try:
        st, d = req("GET", "/health")        # ← 64：保护来得太晚
    except Exception as exc:
        print(f"无法连接后端：{exc}")
```

**原因**：连接被拒抛的是 `urllib.error.URLError`，不是 `HTTPError`，不被捕获。
`cleanup_leftovers()` 又排在健康检查的 try 之前，服务没起时脚本直接 traceback 退出，
看不到"请先启动后端"的提示。第一轮开发时实际踩到过这个现象。

**修正参考**：
```python
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        if isinstance(e, urllib.error.HTTPError):
            raw = e.read().decode("utf-8")
            try:    return e.code, json.loads(raw)
            except Exception: return e.code, raw
        return 0, {"detail": str(e.reason)}     # 连不上：返回 0，让调用方判失败
```

**理由**：测试脚本的第一职责是给出可读结论。连接失败属于预期场景，应当作一次 FAIL 打印，
而不是未捕获异常。修复后 `cleanup_leftovers()` 也能安全执行。

### A3. `delete_node` 的手工置空是冗余的，且绕过 ORM 层

**位置**：`backend/app/crud.py:174-188`

**原文**：
```python
def delete_node(db: Session, node_id: str) -> dict:
    obj = get_node(db, node_id)
    # 边、字段由 ORM 级联删除；note / yaml 的 node_id 置空
    db.execute(
        models.Note.__table__.update().where(models.Note.node_id == node_id).values(node_id=None)
    )
    db.execute(
        models.YamlSnippet.__table__.update()
        .where(models.YamlSnippet.node_id == node_id)
        .values(node_id=None)
    )
    db.delete(obj)
```

**原因**：`models.py` 中 `Note.node_id`、`YamlSnippet.node_id` 的外键已声明
`ondelete="SET NULL"`，且 `db.py` 的连接钩子已执行 `PRAGMA foreign_keys=ON`，
SQLite 在删除父行时会**自动**把这些列置 NULL。这两段 `db.execute` 属于重复劳动。

更实际的隐患：`__table__.update()` 是绕过 ORM 的 Core 语句。如果同一会话里已经加载过
对应的 `Note` 对象，ORM 缓存不会知道这行被改了，后续访问该对象仍拿到旧的 `node_id`。

**修正参考**：
```python
def delete_node(db: Session, node_id: str) -> dict:
    obj = get_node(db, node_id)
    # Note / YamlSnippet 的 node_id 由外键 ondelete="SET NULL" 自动置空；
    # Edge / NodeField 由 ORM cascade 删除
    db.delete(obj)
    audit(db, "delete", "node", node_id, obj.name)
    db.commit()
    return {"deleted": 1, "id": node_id}
```

**理由**：删掉 8 行代码反而更正确——语义由模型层单点声明，不依赖两处手工同步。
若担心 ORM 缓存，可加 `db.expire_all()`，但本项目的会话是"一请求一会话"，实际不会复用到旧对象。

### A4. `import` 的 replace 模式没有事务保护，失败会丢数据

**位置**：`backend/app/crud.py:537-543`

**原文**：
```python
    if mode == "replace":
        for table in (
            models.SopStep, models.Sop, models.Note, models.YamlSnippet,
            models.Edge, models.NodeField, models.Node, models.Group, models.Layer,
        ):
            db.execute(table.__table__.delete())
        db.commit()                      # ← 清空后立刻提交
```

**原因**：清空与随后导入之间有一次 `commit`。若导入数据有问题（例如某条 node 的
`group_id` 指向不存在的分组、或 rows 结构异常），异常抛出时**清空已经落库**，
原数据无法回滚——用户以为"导入失败没关系"，实际库已经被清空。

**修正参考**：
```python
    if mode == "replace":
        try:
            for table in (...):
                db.execute(table.__table__.delete())
            _do_import(db, payload, stats)          # 导入逻辑抽成函数
            audit(db, "import", "atlas", "-", f"mode={mode} " + json.dumps(stats))
            db.commit()                             # 全部成功才提交
        except Exception:
            db.rollback()                           # 任一失败整体回滚
            raise
```

**理由**：replace 是破坏性操作，必须"要么全成功，要么全不动"。这是备份/迁移功能的底线，
README 也把它当作数据安全能力在介绍。

### A5. 导入接口缺少结构校验，任意 JSON 都能进

**位置**：`backend/app/routers/io.py:17-23`

**原文**：
```python
@router.post("/import", summary="导入 JSON 到库（replace 覆盖 / merge 合并）")
def import_data(
    payload: dict,
    mode: str = Query("merge", pattern="^(merge|replace)$"),
    db: Session = Depends(get_db),
):
    return {"mode": mode, "imported": crud.import_all(db, payload, mode), "counts": crud.counts(db)}
```

**原因**：`payload: dict` 只保证顶层是对象。`payload.get("nodes", [])` 若传进来的是字符串或数字，
`for row in rows` 会迭代字符或直接抛 `TypeError`；字段值类型也不校验（`x` 传 `"abc"`
会写进 INTEGER 列，SQLite 类型宽松不报错，读出来时才出问题）。

**修正参考**：
```python
class ImportPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    version: int = 1
    layers:   list[dict] = []
    groups:   list[dict] = []
    nodes:    list[dict] = []
    edges:    list[dict] = []
    notes:    list[dict] = []
    sops:     list[dict] = []
    yamls:    list[dict] = []

@router.post("/import")
def import_data(payload: ImportPayload, mode: str = Query(...), db=Depends(get_db)):
    return crud.import_all(db, payload.model_dump(), mode)
```

**理由**：与 `schemas.py` 对其它接口的强校验保持一致；非法结构在入口就以 422 拒绝，
而不是走到写库环节才炸。

---

## B. 健壮性与安全性

### B1. `drawEdges` 对不存在的节点不判空，整张图的连线会消失

**位置**：`frontend/app.js:262`、`267`

**原文**：
```js
S.graph.edges.forEach(e => {
  if (!S.layerOn[nodeById(e.from_node).layer_id] || !S.layerOn[nodeById(e.to_node).layer_id]) return;
  const A = box(e.from_node), B = box(e.to_node); if (!A || !B) return;   // ← 263 有判空
  ...
  const col = layerColor(nodeById(e.from_node).layer_id);                // ← 267 又取一次
```

**原因**：同一函数里 263 行为 `box()` 结果做了判空，262/267 行却直接解引用 `nodeById(...)`。
一旦 edges 引用了不存在的节点 id（数据竞态：刚删了节点但 `S.graph.edges` 还没刷新），
`nodeById()` 返回 `null`，`.layer_id` 抛 `TypeError`，**整个 drawEdges 中断，所有连线消失**。

**修正参考**：
```js
S.graph.edges.forEach(e => {
  const from = nodeById(e.from_node), to = nodeById(e.to_node);
  if (!from || !to) return;                                   // 先判空，再用
  if (!S.layerOn[from.layer_id] || !S.layerOn[to.layer_id]) return;
  const A = box(e.from_node), B = box(e.to_node); if (!A || !B) return;
  const col = layerColor(from.layer_id);
```

**理由**：把"取节点"和"用节点"合成一步，既消除重复查询（原来一条边查 3 次），
也让判空策略在函数内一致。属于典型的一行修复挡掉整片功能失效。

### B2. `api()` 没有超时与取消机制，后端卡住时前端永久转圈

**位置**：`frontend/app.js:26-39`

**原文**：
```js
async function api(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const text = await res.text();
  ...
}
```

**原因**：`fetch` 默认无超时。后端未响应时 `await` 永久挂起，界面没有任何反馈，
用户看到的就是"点了没反应"——正是验收红线里最怕的那种现象。也没有重试与 AbortController。

**修正参考**：
```js
async function api(path, opts = {}) {
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), 15000);        // 15s 超时
  try {
    const res = await fetch(API + path, {
      headers: { "Content-Type": "application/json" },
      signal: ac.signal, ...opts,
    });
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = text; }
    if (!res.ok) throw new Error((data && data.detail) ? JSON.stringify(data.detail) : (text || res.status));
    return data;
  } catch (err) {
    if (err.name === "AbortError") throw new Error("请求超时（15s），请检查后端是否在运行");
    throw err;
  } finally {
    clearTimeout(timer);
  }
}
```

**理由**：把"静默无响应"变成"明确错误提示"。与 A1 的令牌方案还能共用 `AbortController`
（切节点时取消上一个未完成请求），一并解决竞态与超时。

### B3. `syncLayers` 用 `indexOf` 反查图层，DOM 结构一变就错位

**位置**：`frontend/app.js:152-156`

**原文**：
```js
function syncLayers() {
  document.querySelectorAll(".ck").forEach(d => {
    const l = S.graph.layers.filter(x => x.show_in_filter !== false)[[...document.querySelectorAll(".ck")].indexOf(d)];
    if (l) d.classList.toggle("off", !S.layerOn[l.id]);
  });
```

**原因**：两处问题。① 每次迭代都重新 `querySelectorAll(".ck")` 并 `indexOf`，O(n²)；
② 正确性依赖"DOM 顺序 === 过滤后 layers 的顺序"这个隐式约定——哪天左栏多插一类 `.ck`
（比如加一个"全部显示"复选框），索引就整体偏移，界面勾选状态和实际图层**对不上**，
而 `if (l)` 又会让越界时静默跳过，不报错、极难发现。

**修正参考**：
```js
function syncLayers() {
  const filterable = S.graph.layers.filter(x => x.show_in_filter !== false);
  document.querySelectorAll(".ck").forEach((d, i) => {      // forEach 自带下标
    const l = filterable[i];
    if (l) d.classList.toggle("off", !S.layerOn[l.id]);
  });
```
更稳的做法是构建时就把 id 写到 DOM 上：`d.dataset.id = l.id`，之后按 `d.dataset.id` 取，
彻底不依赖顺序（左栏构建处已有此模式，此处没用上）。

**理由**：隐式顺序耦合是这类"状态与界面不一致"bug 的常见来源。改成显式 id 绑定后，
左栏结构怎么改都不会影响图层同步。

---

## C. 性能

### C1. `drawEdges` 全量重建 SVG，且 hover 高频触发

**位置**：`frontend/app.js:255-258`、`291-292`

**原文**：
```js
function drawEdges() {
  const svg = $("elayer");
  svg.setAttribute("width", 1500); svg.setAttribute("height", 1700);
  svg.innerHTML = "";                       // ← 全清
  ...
}
...
d.onmouseenter = () => { S.hov = n.id; drawEdges(); };   // ← 鼠标划过每张卡都全量重画
d.onmouseleave = () => { S.hov = null; drawEdges(); };
```

**原因**：42 条边 ×（path + 2 circle + g[rect+text]）≈ 210 个 DOM 节点，
每次 hover / select / 缩放 / 平移都整体销毁重建。缩放平移时 `applyT()` 在 mousemove 中
每帧调用，等于每帧重排 210 个节点。当前 41 节点规模尚能跑，但已接近卡顿阈值。

**修正参考**（按收益排序）：
```js
// 1) hover 用 rAF 节流，同帧内多次触发只画一次
let edgeRaf = 0;
function scheduleDrawEdges() {
  if (edgeRaf) return;
  edgeRaf = requestAnimationFrame(() => { edgeRaf = 0; drawEdges(); });
}
// 2) 只在 focus 变化时更新 stroke 透明度，而不是重建整棵 SVG
//    （把 path/circle/text 的引用缓存进 Map<edgeId, {p, c1, c2, t}>，改属性即可）
```

**理由**：这是纯前端渲染层优化，不影响任何接口与数据结构，风险低。
若后续节点数涨到 100+，第 2 条（增量更新）就从"可选"变成"必须"。

### C2. `_merge` 在循环内逐行 `flush`

**位置**：`backend/app/crud.py:545-560`

**原文**：
```python
    def _merge(model, pk, rows):
        n = 0
        for row in rows:
            ...
            n += 1
        db.flush()          # ← 位置对（在循环外）
        return n
```
（同函数在 `crud.py:575`、`581`、`587`、`596`、`602` 的 node / sop 分支中为逐批 flush）

**原因**：`_merge` 本身是循环外 flush，写法正确；但 `import_all` 的 node 与 sop 分支
在 `for row in ...` 内部对每条记录 `db.flush()`，导入 42 个节点 = 42 次语句往返，
且 flush 会触发 ORM 的单位工作逐条提交，导入耗时随数据量线性放大。

**修正参考**：
```python
    for row in payload.get("nodes", []):
        ...
        stats["nodes"] += 1
    db.flush()               # 循环外统一 flush 一次
```

**理由**：flush 的语义是"把待写语句发给数据库"，不需要每行一次。移到循环外，
语句数不变、往返次数从 N 降到 1。导入是大批量操作，这个改动的收益最直接。

---

## D. 规范与可维护性

### D1. `@app.on_event("startup")` 已被 FastAPI 弃用

**位置**：`backend/app/main.py:56`

**原文**：
```python
@app.on_event("startup")
def on_startup():
    models.Base.metadata.create_all(bind=engine)
```

**原因**：FastAPI 自 0.93 起推荐 `lifespan` 上下文管理器替代 `on_event`，
当前版本（0.141.1）仍兼容但会发出 `DeprecationWarning`。同时它无法感知关闭阶段，
做不了优雅停机（例如停机前 flush 审计）。

**修正参考**：
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(_app: FastAPI):
    models.Base.metadata.create_all(bind=engine)
    if SEED_ON_STARTUP:
        db = SessionLocal()
        try:
            if seed_if_empty(db):
                print(f"[atlas] 首次启动：已灌入种子数据 -> {DATABASE_URL}")
        finally:
            db.close()
    yield
    # 关闭阶段可在此释放资源

app = FastAPI(title="K8s Panorama API", version="1.0.0", lifespan=lifespan)
```

**理由**：跟上游推荐写法保持一致，避免未来升级 FastAPI 时突然不工作；
`yield` 之后的部分还给后续"优雅停机"留了位置。

### D2. `config.py` 在模块导入时产生文件系统副作用

**位置**：`backend/app/config.py:12`

**原文**：
```python
DB_PATH = Path(os.getenv("ATLAS_DB", str(DEFAULT_DB)))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)     # ← import 即建目录
DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"
```

**原因**：任何 `import app.config` 的动作都会在磁盘上创建 `backend/data/`。
单元测试、`scripts/_gen_seed.py` 之类只读工具 import 它时，也会留下目录。
副作用应当发生在"确实要用"的时候。

**修正参考**：
```python
DB_PATH = Path(os.getenv("ATLAS_DB", str(DEFAULT_DB)))
DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"

def ensure_db_dir() -> None:
    """在真正建连前调用，避免 import 阶段产生副作用。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
```
在 `db.py` 的 `create_engine` 之前调用一次即可。

**理由**：让 import 变成无副作用操作，是模块可测试、可复用的基本前提。

### D3. datetime 混用带时区与不带时区，比较时会抛异常

**位置**：`backend/app/models.py:12-13`

**原文**：
```python
def _now():
    return datetime.now(timezone.utc)
...
created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
```

**原因**：写入时是 aware（UTC），SQLite 不保存时区信息，读回来是 naive。
于是同一个字段"新建时 aware、查库后 naive"，任何 `created_at > 某个 aware 时间`
的比较都会 `TypeError: can't compare offset-naive and offset-aware datetimes`。
导出时序列化成带 `+00:00` 的字符串，回灌时要靠 `_coerce_row` 特殊处理，也是这个混用的下游成本。

**修正参考**：
```python
def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)   # 统一按 naive UTC 存储
```
或反过来全程 aware 并自定义 TypeDecorator。选前者改动最小，语义（UTC）不变。

**理由**：单一时区表示 eliminates 一整类隐蔽比较错误，也让 `_coerce_row` 的
datetime 还原逻辑可以简化（`fromisoformat` 后 `.replace(tzinfo=None)`）。

### D4. `delete_group(force=True)` 隐式搬迁节点，用户感知为"节点消失"

**位置**：`backend/app/crud.py:88-102`

**原文**：
```python
    if used:  # force：把节点挂到第一个其余分组，避免外键悬空
        other = db.scalars(select(models.Group).where(models.Group.id != group_id)).first()
        if not other:
            raise HTTPException(409, "无法强制删除：系统至少要保留一个分组")
        db.execute(models.Node.__table__.update().where(...).values(group_id=other.id))
```

**原因**：`force=true` 会把该分组下所有节点搬到"排序第一个的其它分组"。
用户以为只是删了个空分组，结果画布上一批组件换了归属——看起来像"节点莫名其妙消失了"。
且目标分组由排序隐式决定，不可控。

**修正参考**：
```python
def delete_group(db, group_id, force=False, move_to=None):
    ...
    if used:
        target = move_to or other
        if not db.get(models.Group, target):
            raise HTTPException(400, f"目标分组不存在：{target}")
        audit(db, "move", "node", "-", f"{used} 个组件从 {group_id} 移至 {target}")
```
接口签名加 `move_to: str | None = None`，明确要求指定去处；不给就用第一个并**在返回里说明**。

**理由**：破坏性操作的目标应当显式。把隐式行为变成显式参数后，
调用方（含将来的前端）必须自己想清楚节点去哪，审计日志也能记下搬迁去向。

### D5. 前端两种渲染范式混用，且 `esc()` 定义在使用点之后

**位置**：`frontend/app.js`（`renderInspector` 约 345 行用 DOM API，`renderNotes` 约 700 行用模板字符串 + `esc()`）

**原文**：
```js
el.appendChild(card("关键属性", () => {           // renderInspector：DOM API
  const box = document.createElement("div");
  ...
}));

return `<h2>知识库</h2>... <p>${esc(t.markdown)}</p>`;   // renderNotes：HTML 字符串
```

**原因**：两条渲染路径并存，新功能该照哪边写没有明确答案；`esc()` 在文件中后段定义，
靠函数提升才能工作，阅读顺序与执行顺序不一致。XSS 防护也因此分散在两处
（DOM API 天然安全，字符串拼接全靠记得调 `esc()`）。

**修正参考**：
- 短期：在文件头部加一段注释，规定"含用户输入的展示一律走 `esc()`；新增面板优先用模板字符串 + `esc()`"，
  并把 `esc()` 挪到文件最前面的工具区。
- 中期：统一为一种范式（推荐 DOM API，安全性由机制保证而非依赖记忆）。

**理由**：`docs/DEVELOPMENT.md` 已把"禁止 innerHTML 拼接用户输入"列为约定，
两种范式并存会让这条约定在执行层出现灰色地带。统一后约定才可机械检查。

---

## 汇总

| 分组 | 数量 | 最严重的一项 |
|---|---|---|
| A 功能性缺陷 | 5 | A1 详情面板异步竞态（用户看到错误内容） |
| B 健壮性与安全性 | 3 | B1 节点判空缺失（整片连线消失） |
| C 性能 | 2 | C1 SVG 全量重建 + hover 高频触发 |
| D 规范与可维护性 | 5 | D3 datetime aware/naive 混用 |
| **合计** | **15** | |

**修复优先级建议**：A1 → A2 → A4 → A5 → B1 → B2 → B3 → D3，其余可排在下个迭代。
A1、A4、B1 三项共同点是"用户操作后结果不正确或数据可能丢失"，与项目对外宣称的
"点击后必须有真实效果"直接相关，建议优先处理。

**本次未修改任何代码**，上述"修正参考"均需人工评估后再决定是否采纳。

---


---

## 修复状态（2026-09-26）

以下 15 项已全部修复并通过回归验证。**未新增范围外改动**，每项对应上文编号。

| 编号 | 状态 | 验证证据 |
|---|---|---|
| A1 详情面板异步竞态 | fixed | 注入测试：连续 select pod→kubelet→netpol，右栏标题为 NetworkPolicy，「相关知识条目」卡片只出现 1 次 |
| A2 测试脚本连接失败崩溃 | fixed | 停掉后端跑 `python scripts/test_api.py`，输出 `FAIL 健康检查返回 200` + 「后端未就绪」，无 traceback |
| A3 delete_node 冗余置空 | fixed | 建关联 note 后删组件，`GET /notes/{slug}` 返回 `node_id: null` 且条目本身仍在 |
| A4 replace 导入无事务 | fixed | replace 导入含坏 group_id 的数据 → 返回 400「已整体回滚」；组件数 41→41，`apiserver` 仍在 |
| A5 导入无结构校验 | fixed | `{"nodes":"not-a-list"}`、`{"layers":123}` 均返回 422 |
| B1 drawEdges 未判空 | fixed | 注入一条指向不存在节点的边，drawEdges 不抛错，其余 42 条连线照画 |
| B2 api() 无超时 | fixed | 代码含 AbortController + 15s 超时 + AbortError 明确提示（注入测试断言通过） |
| B3 syncLayers indexOf 反查 | fixed | 改为 forEach 下标 + filterable 数组，不再每次重新 querySelectorAll |
| C1 drawEdges 全量重建 | fixed | 全部 8 个调用点改走 `scheduleDrawEdges()` 合帧；另加 setTimeout 兜底（无头环境 rAF 不触发时连线仍能画出） |
| C2 _merge 循环内 flush | fixed | node / sop 分支的 flush 移到循环外，语句往返从 N 次降到 1 次 |
| D1 on_event 弃用 | fixed | 改用 `lifespan` 异步上下文管理器，服务启动与健康检查正常 |
| D2 config import 副作用 | fixed | 拆出 `ensure_db_dir()`，由 db.py 在建 engine 前调用 |
| D3 datetime aware/naive 混用 | fixed | `models._now()` 与 `crud._utcnow()` 统一返回 naive UTC；导出 `created_at` 已无 `+00:00` 后缀 |
| D4 delete_group 隐式搬迁 | fixed | 新增 `move_to` 参数：合法目标返回 `moved_to`；不存在的目标返回 400 且分组与组件都不动 |
| D5 前端两种渲染范式混用 | fixed | `esc()` 前移至文件首部工具区（删除了重复定义），并在文件头写明渲染范式约定 |

### 回归结果

| 测试 | 结果 |
|---|---|
| `python scripts/test_api.py`（原有 50 项断言） | **PASS 50 / FAIL 0** |
| 修复专项验证（A3/A4/A5/D3/D4，18 项断言） | **PASS 18 / FAIL 0** |
| 前端注入测试（A1/B1/B2/C1/D5 + 首屏/搜索/图层/页签，12 项断言） | **PASS 12 / FAIL 0** |

合计 **80 项断言全部通过**。回归后数据库计数回到 41 组件 / 42 关系，无残留测试数据。

### 顺带修掉的一个衍生问题

A4 修复后首轮专项验证发现：导入失败时异常直接冒泡成 `500 Internal Server Error`，
调用方看不到原因。已在 `crud.import_all` 的 `except` 分支把异常转成
`HTTPException(400, "导入失败，已整体回滚，数据未改动：...")`，
该场景现返回 400 且 detail 含具体原因（见 A4 的验证输出）。
