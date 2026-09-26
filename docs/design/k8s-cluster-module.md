# K8s 集群接入模块设计（独立模块 · 只读）

> 状态：方案评审中，尚未开始实现。
> 前置结论（来自用户反馈）：全景架构图定位是**故障排查导航**，不是集群镜像；
> 接入真实集群必须**单独成模块**，不得与现有全景图冲突。本文件即该模块的详细设计。

---

## 1. 为什么必须独立成模块（冲突点分析）

把集群数据直接画进现有全景图，会撞上六类冲突。这些不是"小心一点就能避免"的问题，是**两种数据在本体上不同**：

| # | 冲突 | 具体表现 |
|---|---|---|
| 1 | **数据语义冲突** | 全景图是概念全集（41 个组件），集群视图是实例快照。混在一张图上，用户会困惑"图上画了 Gateway API，但我集群里没有" |
| 2 | **坐标冲突** | 全景图用手写坐标表达逻辑层次（① 控制面在上、⑨ 可观测在下）。集群视图需要按实际拓扑和状态排列，两套布局诉求互斥 |
| 3 | **生命周期冲突** | 知识数据是慢变量（随版本发布），集群状态是快变量（秒级）。同一套缓存/刷新/失效策略不可能同时适用 |
| 4 | **故障域冲突** | 全景图数据在本地 SQLite，永不失效。集群不可达时若共用渲染路径，会把一个外部依赖的故障变成全站故障 |
| 5 | **写权限冲突** | 知识库需要 CRUD，集群必须只读。同一套鉴权模型会把"谁能改知识"和"谁能看集群"搅在一起 |
| 6 | **演进冲突** | 全景图随参考图固定；集群视图要跟着 K8s 版本、CRD、CNI 方案持续演进 |

**结论：不是"加个接口"，是加一个有自己边界的模块。**

---

## 2. 模块划分

```
backend/app/cluster/                 ← 新增独立子包
├── __init__.py
├── router.py        # 只挂 /api/cluster/*；不 import atlas 的任何东西
├── client.py        # kube-apiserver 只读客户端（超时 / 重试 / 连接池 / 降级）
├── mapper.py        # K8s 对象 → 图谱组件 ID 的映射规则（纯函数，可单测）
├── cache.py         # TTL 内存缓存，与 atlas 的内存态完全隔离
├── snapshot.py      # 集群快照数据结构（Node/Pod/Service/Ingress/Policy 的实存状态）
└── errors.py        # 集群不可达的统一降级错误类型

frontend/
├── app.js           # 新增「集群视图」分支，不改全景图的渲染路径
└── cluster-view.js  # 集群视图独立渲染（可选拆分，避免 app.js 继续膨胀）
```

**各模块职责与边界：**

| 模块 | 负责 | 明确不负责 |
|---|---|---|
| `client.py` | 与 kube-apiserver 通信、超时、重试、连接复用、错误归一 | 不解析业务语义，不做映射判断 |
| `mapper.py` | 把 K8s 对象归一到图谱组件 ID（纯函数） | 不发请求，不碰数据库 |
| `cache.py` | TTL 缓存、并发去重（同 key 只打一次 API） | 不落盘，不做历史 |
| `snapshot.py` | 定义集群快照的结构与派生指标（如 Node Ready 比例） | 不做 HTTP 序列化细节 |
| `router.py` | 暴露只读接口，把降级错误转成 503 + 明确 detail | 不写库，不调 atlas 的 crud |

---

## 3. 冲突规避的六条铁律

### 铁律 1：路由物理隔离

```python
# main.py —— 两组路由分开注册，cluster 的任何异常不波及 atlas
app.include_router(atlas.router,  prefix="/api/atlas")
app.include_router(cluster.router, prefix="/api/cluster")   # 新增
```

`cluster` 包内**禁止** `from . import crud` / `from .routers import atlas`。
用 import 层面的隔离把"误用知识库写路径"这条路直接焊死。

### 铁律 2：数据不混表

集群状态**只进内存缓存**（`cache.py`），需要历史时进独立的 `cluster_snapshot` 表（带 TTL 语义、可定期清理）。

**绝不写入 `node` / `edge` / `node_field`。** 那三张表是知识数据的家，被集群快照污染一次，全景图就再也不是"概念全集"了。

```
SQLite
├── layer / atlas_group / node / node_field / edge    ← 知识数据（慢变量，人工维护）
├── note / sop / sop_step / yaml_snippet              ← 知识内容
├── audit_log                                         ← 写操作留痕
└── cluster_snapshot（可选）                           ← 集群快照（快变量，TTL 清理）
```

### 铁律 3：布局共享，数据分离

**布局坐标是心智锚点，必须与全景图一致；要隔离的是数据源，不是坐标。**

集群视图**直接复用** `atlas_group`（8 个分组容器）与 `node`（41 个组件）的 `x/y/w/h` 作为**固定槽位（Slot）**，
不重新推导拓扑坐标。理由是：

- 排障时"图上位置"必须是稳定锚点 —— 用户在全景图学到"① 控制面在最上面"，
  切到集群视图不该重新学一遍布局
- 槽位固定 → 未检测到的组件有地方可去（置灰标注），而不是让整张图重新流动
- 实现上零坐标转换成本，渲染器可完整复用

> 注：本条由"视图不共舞台"修正而来。原先担心共用坐标会导致数据混淆，
> 实际要防的是**数据混用与渲染路径互相污染**，不是坐标复用。坐标是布局，不是数据。
> 真正被否决的是"在同一张图上叠加两层数据互相覆盖"的 overlay 方案 ——
> 那会让用户分不清哪层是概念、哪层是实况。集群视图是**独立页签、独立数据源、同一套槽位坐标**。

集群专属的实测关系（如某 Node 上实际跑了哪些 Pod）以**独立连线样式**叠加在槽位关系之上，
不替代、不覆盖概念连线，详见第 6.3 节。

### 铁律 4：只读边界

`client.py` 用白名单方式实现，而不是黑名单：

```python
ALLOWED_METHODS = ("GET",)          # 只有 GET

class ReadOnlyKubeClient:
    def get(self, path: str, **kw):        # 唯一对外方法
        return self._request("GET", path, **kw)
    # 没有 post / put / patch / delete 方法 —— 不是"不调用"，是"不存在"
```

配合 ServiceAccount 侧的最小 RBAC（只授 `get/list/watch`，不授 `create/update/delete`），
形成**代码层 + 集群层双重只读边界**。这一点面试很好讲：两道防线各自独立失效都不会导致误写。

### 铁律 5：故障不传染

集群不可达时：

```
GET /api/cluster/status
  → 503 {"detail": "cluster unreachable: ...", "degraded": true}
```

前端行为：
- 顶栏显示「集群未连接」徽标（灰色，可点击查看原因）
- 「集群视图」页签显示空状态 + 重试按钮
- **其余五个页签功能完全正常**（它们本来就不依赖集群）

原则：**集群模块的失效永远是一个局部降级，不是全站故障。**

### 铁律 6：凭证隔离

```
ATLAS_KUBECONFIG=/path/to/kubeconfig      # 只被 cluster 模块读取
ATLAS_K8S_TIMEOUT=5                        # 秒
ATLAS_K8S_CACHE_TTL=10                     # 秒
```

这些配置项只出现在 `cluster/` 的文档里，不进 `config.py` 的通用配置表，
避免"改 atlas 配置顺手影响集群模块"。

---

## 4. 映射规则（mapper 的核心决策）

把 K8s 对象归一到图谱组件 ID：

| K8s 对象 | 映射到图谱 ID | 说明 |
|---|---|---|
| `kube-apiserver` 自身可达性 | `apiserver` | 由 `/version`、`/healthz` 推导 |
| Node 对象（聚合） | `node` | 按 Ready/NotReady 汇总，不是一个 Node 一张卡 |
| Pod（聚合） | `pod` | 按 Running/Pending/Failed 汇总计数 |
| Service | `service` | 按类型汇总 |
| EndpointSlice | `endpointslice` | 统计有后端 vs 空后端 |
| Ingress / Gateway API | `ingress` / `gateway` | **按 CRD 是否存在判断**，不存在则标「未检测到」 |
| CNI | `cni` | 通过 Node 上运行的 DaemonSet 名称探测 flannel/calico/cilium |
| NetworkPolicy | `netpol` | 有策略且选中了 Pod → 提示"可能拦截" |
| Prometheus / metrics-server | `prometheus` / `metricsserver` | 按 Deployment/APIService 存在性判断 |

**关键规则：未检测到 ≠ 不存在。**

集群里没有的组件，在全景图上显示为「集群中未检测到」的置灰标注，**卡片本身不消失**。
这是"全景图是概念全集，集群层只做状态标注"这条心智模型的直接落地。

---

## 5. 接口设计（新增，不动旧契约）

```
GET /api/cluster/status
    集群可达性、版本、Node/Pod 汇总计数、采集耗时
    不可达 → 503 + {"degraded": true, "reason": "..."}

GET /api/cluster/components
    图谱组件 ID → 集群实存状态的标注列表
    [{"component_id":"apiserver","state":"present","detail":"v1.29.3"},
     {"component_id":"gateway","state":"not_detected","detail":"Gateway API CRD 不存在"}]

GET /api/cluster/nodes
    Node 列表（名称、Ready、kubelet 版本、容器运行时、可分配资源）

GET /api/cluster/workloads?namespace=
    工作负载汇总（Deployment/StatefulSet/DaemonSet 的期望/就绪副本）
```

**state 只有四个取值**：`present` / `not_detected` / `unhealthy` / `unknown`。
不设计更细的状态机 —— 集群层只做"在不在、好不好"，深度诊断留给排障 SOP。

**旧接口零改动**：`/api/atlas/graph`、`/api/nodes` 等一个字段都不加。
前端拿全景图数据 + 集群标注数据，在**前端**做合并展示，不在后端合。
这样后端两条链路可以独立演进、独立测试、独立回滚。

---

## 6. 资源可视化展示方案（集群视图）

> 目标：参照全景图的层级布局预规划固定槽位，集群连接后按实际运行状态自动填充，
> 连线清晰呈现关联，交互体验与全景图一致，右栏附带可直接参考的操作命令。

### 6.1 层级与槽位规划

全景图的 8 个分组归为 **6 个逻辑层**，每层槽位坐标直接取全景图数据，集群连接后按实况填充：

| 层 | 名称 | 对应分组 | 槽位数 | 填充内容（集群实况） |
|---|---|---|---|---|
| **L1** | 控制面 | ① | 7 | apiserver / etcd / scheduler / kcm / ccm / admission / coredns 的可达性与版本 |
| **L2** | 节点与网络底座 | ② + ③ | 11 | Node Ready 汇总、CNI 探测结果、kube-proxy 模式、Service/EndpointSlice 数量、NetworkPolicy 命中情况 |
| **L3** | 入口与流量 | ④ | 4 | Ingress / Gateway / HTTPRoute 是否安装及路由条数 |
| **L4** | 工作负载 | ⑤ | 6 | Pod 按状态汇总、Deployment/StatefulSet/DaemonSet/Job 期望 vs 就绪副本、HPA 当前/目标 |
| **L5** | 存储与安全 | ⑦ + ⑧ | 9 | PVC Bound 比例、PV 状态、StorageClass 是否默认、RBAC/SA/Secret 计数、PSA 级别 |
| **L6** | 可观测 | ⑨ | 4 | metrics-server / Prometheus / 日志 agent 是否在位、targets up 比例 |

**槽位四态**（一个槽位在集群视图下的全部可能）：

| 状态 | 视觉 | 含义 |
|---|---|---|
| `present` + healthy | 分类色实线描边 | 组件在位且正常 |
| `present` + unhealthy | 琥珀/红色描边 + 轻微脉冲 | 在位但有问题（如 Node NotReady） |
| `not_detected` | 置灰 + 虚线描边 + 「未检测到」角标 | 集群里没装这个概念 |
| `unknown` | 半透明 + 「采集失败」提示 | 探测过程出错，不阻断其他槽位 |

**关键规则：未检测到 ≠ 不存在。** 槽位永远占着，卡片永不消失 —— 全景图是概念全集这条心智模型在集群视图继续成立。

**卡片内容从"概念"切换为"实况"**，例如：

```
全景架构（概念）                集群视图（实况）
─────────────────              ─────────────────
Pod                            Pod
最小调度单元                    就绪 12 / 13
承载：liveness/readiness        Pending 1 · Failed 0
                               CrashLoop 0
```

### 6.2 交互体验与全景图保持一致

直接复用全景图的画布组件与手势，**不写第二套**：

| 交互 | 集群视图行为 |
|---|---|
| 滚轮缩放 / 空白拖动 / 双击放大 | 与全景图完全一致（含 LOD 分级） |
| 拖动组件挪位 | 与全景图一致（仅当前会话有效，不写库） |
| 顶部图例 / 左栏图层过滤 | 与全景图一致，8 分类通用 |
| 左栏「视图」聚焦 | 与全景图一致（L1~L6 可按层聚焦） |
| 点击组件 → 右栏 | 面板结构一致，内容切换为「实况 + 命令」 |
| 顶栏「链路」「动画」开关 | 同样生效 |

顶部页签并列，切换无跳变（因为坐标相同）：

```
[全景架构] [集群视图] [网络链路] [对照表] [知识库] [排障 SOP] [YAML 实验室]
   概念数据    实况数据（同一套槽位）
```

### 6.3 连线设计：概念关系 + 实测关系分层呈现

两类连线**同时存在、样式可辨**，不互相覆盖：

| 类型 | 来源 | 样式 | 含义 |
|---|---|---|---|
| **概念连线** | `edge` 表（41→42 条，静态） | 实线 + 分类色，标签为关系词 | "这两个组件本该有关系" |
| **实测连线** | `cluster.mapper` 动态生成 | 点线（dashed）+ 中性灰蓝 | "你的集群里它们实际这样连着" |

实测连线示例：某 Node → 其上实际运行的 Pod 集合；Service → 其真实 EndpointSlice 后端；
Ingress → 它实际路由到的 Service。

**状态联动规则**：
- 概念连线任一端 `unhealthy` → 该连线转琥珀色并加粗（提示"这条链路上有东西坏了"）
- 概念连线任一端 `not_detected` → 置灰虚线，不吸引注意
- 实测连线只连接 `present` 的槽位；一端不是 `present` 就不画

这样排查时能直接看出"哪条概念链路上的实际组件出了问题"。

### 6.4 右栏：实况详情 + 可执行命令面板

右栏保留与全景图一致的五卡结构，但内容与新增卡片如下：

```
┌─────────────────────────────┐
│ Pod                    〔集群实况〕│  ← 数据来源徽标，与知识库来源区分
│ 就绪 12 / 13                │
├─────────────────────────────┤
│ ▸ 实况摘要                   │  ← 原「关键属性」卡：按状态计数
├─────────────────────────────┤
│ ▸ 实例列表                   │  ← 新增：实际对象（名称/状态/重启次数/age）
│   api-7d9f-abcde  Running 0 2d │     点击可把名称带入下方命令
│   api-7d9f-ff123  Pending 0 4m│
├─────────────────────────────┤
│ ▸ 上下游（实况）              │  ← 原「上下游」卡：标注集群实测关系
├─────────────────────────────┤
│ ▸ 常用命令            〔复制〕│  ← 新增，核心
│   kubectl get pods -o wide   │
│   kubectl describe pod api-… │  ← 已填入实例名，复制即可执行
│   kubectl logs api-… --tail=100 │
│   kubectl top pods           │
├─────────────────────────────┤
│ ▸ 相关知识条目                │  ← 与全景图共用，仍来自 /api/notes
└─────────────────────────────┘
```

**命令面板的三条设计原则：**

1. **参数化，不是静态列表** —— 命令模板里的资源名用集群实况填充
   （`kubectl describe pod <真实名>`），用户复制粘贴即可执行，不用自己改名字
2. **异常时命令重排** —— 槽位 `unhealthy` 时，把最能定位问题的命令置顶
   （Pod Pending → `kubectl describe pod` 第一；Node NotReady → `kubectl describe node` 第一）
3. **只读边界在命令层也成立** —— 命令面板**可以**包含 `kubectl edit` / `kubectl patch` 这类改配置的命令
   （用户明确提到"调整配置"），但它们只是**文本**，由用户复制到自己的终端执行；
   后端永远不代执行。界面上会对写操作命令加「写」标记，与只读命令视觉区分。

### 6.5 降级与空状态

| 场景 | 表现 |
|---|---|
| 未配置 kubeconfig | 「集群视图」页签显示引导卡：如何生成 SA、如何配置路径、需要哪些 RBAC |
| 配置了但连不上 | 顶栏灰色「集群未连接」徽标 + 页签内错误原因 + 「重试」按钮；其他页签零影响 |
| 连上但部分 API 无权限 | 对应槽位 `unknown` + 提示缺哪个 verb；不阻塞其他槽位 |
| 采集超时 | 用上一次成功快照（TTL 内）+ 「数据可能过期」提示 |

---

## 7. 资源可视化验收清单（M2b 出口标准）

| # | 验收项 | 验证方式 |
|---|---|---|
| 1 | 集群视图槽位坐标与全景图完全一致 | 截屏对比两视图，分组框与卡片位置无偏移 |
| 2 | 未安装的组件在集群视图中置灰显示「未检测到」，卡片不消失 | 无 Gateway API 的集群上截图 |
| 3 | 异常组件（如 Node NotReady）有告警描边，且关联概念连线转琥珀色 | 制造一个 NotReady Node 后观察 |
| 4 | 实测连线与概念连线样式可辨，不互相覆盖 | 截屏 + 图例说明 |
| 5 | 右栏命令已填入真实资源名，复制即可执行 | 点开一个 Pod，检查命令中的 name |
| 6 | 异常时定位命令置顶（Pod Pending → `describe pod` 第一） | 制造 Pending Pod 后观察右栏排序 |
| 7 | 写操作命令有「写」标记，与只读命令视觉区分 | 观察 `kubectl edit` 类命令的呈现 |
| 8 | 集群断开后集群视图降级，其他页签功能正常 | 停掉 apiserver 或改错 kubeconfig，跑 `test_api.py` 应仍 50 PASS |

---

## 8. 验收清单（M2 总体出口标准）

| # | 验收项 | 验证方式 |
|---|---|---|
| 1 | 无 kubeconfig 时服务照常启动，五个原页签功能正常 | 删掉配置文件，重启，跑 `test_api.py` 应 50 PASS |
| 2 | `/api/cluster/status` 在无集群时返回 503 + `degraded:true`，不是 500 | curl |
| 3 | 集群可达时 `/api/cluster/components` 返回标注，`apiserver` 为 `present` | curl（有集群的同学实测） |
| 4 | 集群里不存在的组件返回 `not_detected`，且全景图卡片不消失 | 前端截图对比 |
| 5 | `cluster` 包内无任何写方法 | `grep -E "def (post|put|patch|delete)" backend/app/cluster/` 为空 |
| 6 | `cluster` 包不 import atlas / crud | `grep -rE "from \.(routers )?(atlas|crud)" backend/app/cluster/` 为空 |
| 7 | 集群接口超时不拖慢其他接口 | 并发打 `/api/health` 与 `/api/cluster/status`，前者响应时间不受影响 |
| 8 | ServiceAccount 只有只读权限 | `kubectl auth can-i create pods` → `no` |

---

## 9. 风险与缓解

| 风险 | 缓解 |
|---|---|
| kubeconfig 格式/路径在 Windows 与 Linux 不一致 | 统一走 `KUBECONFIG` 环境变量 + `~/.kube/config` 兜底，路径解析集中在 `client.py` 一处 |
| 集群 API 限流或大面积 list 拖慢响应 | TTL 缓存 + 同 key 并发去重；只 list 必要的 namespace；不 `--watch` |
| 不同 K8s 版本字段差异 | `mapper.py` 全部用 `.get()` 容错，缺失字段归 `unknown`，不抛异常 |
| 误接生产集群造成心理压力 | README 与配置项明示"只读"，且默认超时 5s；首次连接需显式配置，不自动发现 |
| 快照落库后无限增长 | 若启用 `cluster_snapshot`，配 TTL 清理任务，默认只留内存 |

---

## 10. 与排障闭环（M3）的关系

集群模块是排障演练的**事实来源**：演练时的"集群实况"由它提供，
判分逻辑比对"用户查了的对象"与"真实异常对象"是否一致。
但 M3 可以在 M2 之前用**内置故障剧本**（mock 集群状态）先跑起来，
不必阻塞等待真实集群接入 —— 两条线可以并行。
