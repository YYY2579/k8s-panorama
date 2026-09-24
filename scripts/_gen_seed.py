"""一次性工具：从已核对过参考图的 k8s-panorama.html 中提取图谱数据，生成 backend/app/seed.py。

这样种子数据 100% 与参考图逐字核对过的那份一致，避免手工转录出错。
运行一次即可：python scripts/_gen_seed.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT.parent / "k8s-panorama.html"   # 工作区根目录下那份已核对的复刻版
OUT = PROJECT / "backend" / "app" / "seed.py"

if not SRC.exists():
    raise SystemExit(f"找不到源文件：{SRC}")

src = SRC.read_text(encoding="utf-8")


def block(name: str) -> str:
    m = re.search(r"const " + name + r" = \[(.*?)\n\];", src, re.S)
    if not m:
        raise SystemExit(f"源文件中找不到 const {name}")
    return m.group(1)


# ---------------- LAYERS ----------------
layers = []
for m in re.finditer(r"\{id:'([^']+)',\s*label:'([^']+)',\s*color:'([^']+)'\}", block("LAYERS")):
    layers.append({"id": m.group(1), "label": m.group(2), "color": m.group(3)})

# ---------------- GROUPS ----------------
groups = []
for m in re.finditer(
    r"\{id:'([^']+)',\s*no:'([^']+)',\s*title:'([^']+)',\s*sub:'([^']*)',\s*x:(\d+),\s*y:(\d+),\s*w:(\d+),\s*h:(\d+)\}",
    block("GROUPS"),
):
    groups.append(
        {
            "id": m.group(1),
            "ordinal": m.group(2),
            "title": m.group(3),
            "subtitle": m.group(4),
            "x": int(m.group(5)),
            "y": int(m.group(6)),
            "w": int(m.group(7)),
            "h": int(m.group(8)),
        }
    )

# ---------------- NODES ----------------
nodes = []
node_re = re.compile(
    r"\{id:'(?P<id>[^']+)',\s*g:'(?P<g>[^']+)',\s*x:(?P<x>\d+),\s*y:(?P<y>\d+),\s*l:'(?P<l>[^']+)',\s*"
    r"n:'(?P<n>[^']+)',\s*k:'(?P<k>[^']+)',\s*f:\[(?P<f>.*?)\],\s*"
    r"cmd:'(?P<cmd>[^']*)',\s*sum:'(?P<sum>.*?)'\}",
    re.S,
)
for m in node_re.finditer(block("NODES")):
    fields = [list(t) for t in re.findall(r"\['([^']*)',\s*'([^']*)'\]", m.group("f"))]
    nodes.append(
        {
            "id": m.group("id"),
            "group_id": m.group("g"),
            "layer_id": m.group("l"),
            "name": m.group("n"),
            "kind": m.group("k"),
            "summary": m.group("sum"),
            "cmd": m.group("cmd"),
            "x": int(m.group("x")),
            "y": int(m.group("y")),
            "fields": [{"label": a, "value": b} for a, b in fields],
        }
    )

# ---------------- EDGES ----------------
layer_of = {n["id"]: n["layer_id"] for n in nodes}
edges = []
for i, m in enumerate(re.finditer(r"\{a:'([^']+)',\s*b:'([^']+)',\s*t:'([^']*)'\}", block("EDGES"))):
    a, b, t = m.group(1), m.group(2), m.group(3)
    edges.append(
        {
            "id": f"{a}->{b}",
            "from_node": a,
            "to_node": b,
            "label": t,
            "layer_id": layer_of.get(a),
            "sort_order": i,
        }
    )

print(f"parsed: layers={len(layers)} groups={len(groups)} nodes={len(nodes)} edges={len(edges)}")
if not (len(layers) == 8 and len(groups) == 8 and len(nodes) == 41 and len(edges) == 42):
    print("!! 数量与预期不符，请检查正则是否漏匹配")


def py(obj, indent=0):
    return json.dumps(obj, ensure_ascii=False, indent=2).replace("\n", "\n" + " " * indent)


HEADER = '''"""种子数据：首次启动时建表并灌入。

数据来源：与参考图逐字核对过的图谱数据（41 个组件 / 42 条关系 / 8 个分组 / 8 个分类），
由 scripts/_gen_seed.py 从复刻版 HTML 中自动提取，未经手工转录。

知识条目 / 排障 SOP / YAML 片段为可编辑的示例内容，在界面上就能改。
"""
'''
NOTES_DEF = '''
NOTES = [
    {
        "slug": "networkpolicy-basics",
        "node_id": "netpol",
        "title": "NetworkPolicy：默认拒绝与放行",
        "status": "published",
        "markdown": (
            "## 核心语义\\n\\n"
            "NetworkPolicy 按 Pod 选择器控制 L3/L4 进出。**默认未选中的 Pod 允许所有流量**；"
            "一旦被策略选中，未允许的入站（或出站，若声明 Egress）被拒绝。\\n\\n"
            "## 常见坑\\n\\n"
            "1. 策略需要 CNI 实现。Flannel 默认不生效，Calico / Cilium 才支持。\\n"
            "2. podSelector 为空表示选中命名空间下全部 Pod。\\n"
            "3. 只声明 ingress 不影响 egress，反之亦然。\\n\\n"
            "## 一句话记忆\\n\\n"
            "Route 决定去哪，Policy 决定是否允许。"
        ),
    },
    {
        "slug": "service-endpointslice",
        "node_id": "service",
        "title": "Service 到 Pod：中间还隔着 EndpointSlice",
        "status": "published",
        "markdown": (
            "Service 的 ClusterIP 只是**虚拟 IP**，真正转发的目标是 EndpointSlice 里记录的地址。\\n\\n"
            "排查 502 / 超时时的顺序：\\n\\n"
            "1. `kubectl get endpointslice -A` 看后端地址在不在；\\n"
            "2. 地址为空 → 回去查 selector 是否匹配上 Pod 标签；\\n"
            "3. 地址在但不通 → 查 kube-proxy 规则 / CNI / NetworkPolicy。"
        ),
    },
    {
        "slug": "pod-pending-triage",
        "node_id": "pod",
        "title": "Pod 一直 Pending 怎么查",
        "status": "draft",
        "markdown": (
            "按顺序排除：\\n\\n"
            "1. `kubectl describe pod` 看 Events；\\n"
            "2. 调度失败 → 资源不足 / 污点 / 亲和性；\\n"
            "3. 镜像拉取失败 → 仓库地址、密钥、网络；\\n"
            "4. 存储问题 → PVC 是否 Bound。"
        ),
    },
]
'''
SOPS_DEF = '''
SOPS = [
    {
        "symptom": "service-502",
        "title": "访问 Service 返回 502 / 连接被拒",
        "status": "published",
        "steps": [
            {"step_no": 1, "action": "确认 Service 是否存在且 selector 正确",
             "expect": "Service 存在，selector 能匹配到预期 Pod",
             "command": "kubectl get svc -A -o wide"},
            {"step_no": 2, "action": "检查后端地址是否就绪（EndpointSlice）",
             "expect": "能看到与 Pod 数量一致的 endpoint，且 ready=true",
             "command": "kubectl get endpointslice -A"},
            {"step_no": 3, "action": "确认 Pod 处于 Running 且探针通过",
             "expect": "READY 为 1/1，无 CrashLoopBackOff",
             "command": "kubectl get pods -o wide"},
            {"step_no": 4, "action": "检查是否有 NetworkPolicy 拦截",
             "expect": "策略允许入口流量，或该 Pod 未被任何策略选中",
             "command": "kubectl get networkpolicy -A"},
            {"step_no": 5, "action": "在节点上直连 Pod IP 验证",
             "expect": "能直连说明问题在 Service 转发层，不能直连说明在 CNI 或应用本身",
             "command": "kubectl exec -it <pod> -- curl -sv localhost:<port>"},
        ],
    },
    {
        "symptom": "pod-pending",
        "title": "Pod 长时间处于 Pending",
        "status": "draft",
        "steps": [
            {"step_no": 1, "action": "查看事件",
             "expect": "Events 里能看出是调度失败还是拉取失败",
             "command": "kubectl describe pod <pod>"},
            {"step_no": 2, "action": "看节点可分配资源与污点",
             "expect": "存在资源足够的节点，且 Pod 能容忍其污点",
             "command": "kubectl describe nodes | grep -A5 'Taints\\|Allocated'"},
            {"step_no": 3, "action": "检查 PVC 是否已绑定",
             "expect": "相关 PVC 状态为 Bound",
             "command": "kubectl get pvc -A"},
        ],
    },
]
'''
YAMLS_DEF = '''
YAMLS = [
    {
        "node_id": "netpol",
        "title": "最小可用的 NetworkPolicy（默认拒绝入站）",
        "yaml": (
            "apiVersion: networking.k8s.io/v1\\n"
            "kind: NetworkPolicy\\n"
            "metadata:\\n"
            "  name: default-deny-ingress\\n"
            "  namespace: demo\\n"
            "spec:\\n"
            "  podSelector: {}          # 选中本命名空间全部 Pod\\n"
            "  policyTypes: [\\"Ingress\\"]\\n"
        ),
    },
    {
        "node_id": "deployment",
        "title": "最小可用的 Deployment",
        "yaml": (
            "apiVersion: apps/v1\\n"
            "kind: Deployment\\n"
            "metadata:\\n"
            "  name: demo\\n"
            "spec:\\n"
            "  replicas: 2\\n"
            "  selector:\\n"
            "    matchLabels:\\n"
            "      app: demo\\n"
            "  template:\\n"
            "    metadata:\\n"
            "      labels:\\n"
            "        app: demo\\n"
            "    spec:\\n"
            "      containers:\\n"
            "        - name: app\\n"
            "          image: nginx:1.25\\n"
            "          ports:\\n"
            "            - containerPort: 80\\n"
        ),
    },
]
'''
BODY = '''

def seed_if_empty(db) -> bool:
    """库里没有组件时才灌种子数据。返回是否执行了灌入。

    幂等：重复启动不会重复写入，也不会覆盖用户后来新增/修改过的内容。
    """
    from . import models
    from .crud import audit
    from sqlalchemy import select, func

    n = db.scalar(select(func.count()).select_from(models.Node)) or 0
    if n:
        return False

    for i, row in enumerate(LAYERS):
        db.merge(models.Layer(**row, sort_order=i))
    db.flush()

    for i, row in enumerate(GROUPS):
        db.merge(models.Group(**row, sort_order=i))
    db.flush()

    for row in NODES:
        fields = row.pop("fields", [])
        obj = models.Node(**row)
        obj.fields = [
            models.NodeField(label=f.get("label", ""), value=f.get("value", ""), sort_order=i)
            for i, f in enumerate(fields)
        ]
        db.merge(obj)
    db.flush()

    for row in EDGES:
        db.merge(models.Edge(**row))
    db.flush()

    for row in NOTES:
        db.merge(models.Note(**row))
    db.flush()

    for row in SOPS:
        steps = row.pop("steps", [])
        obj = models.Sop(**row)
        obj.steps = [models.SopStep(**s) for s in steps]
        db.merge(obj)
    db.flush()

    for row in YAMLS:
        db.add(models.YamlSnippet(**row))

    audit(db, "seed", "atlas", "-",
          f"layers={len(LAYERS)} groups={len(GROUPS)} nodes={len(NODES)} "
          f"edges={len(EDGES)} notes={len(NOTES)} sops={len(SOPS)} yamls={len(YAMLS)}")
    db.commit()
    return True
'''


content = (
    HEADER
    + "\nLAYERS = " + py(layers) + "\n"
    + "\nGROUPS = " + py(groups) + "\n"
    + "\nNODES = " + py(nodes) + "\n"
    + "\nEDGES = " + py(edges) + "\n"
    + NOTES_DEF + SOPS_DEF + YAMLS_DEF + BODY
)

OUT.write_text(content, encoding="utf-8")
print(f"written -> {OUT}  ({len(content)} chars)")
