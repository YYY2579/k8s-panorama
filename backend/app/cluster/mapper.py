"""把 K8s API 对象归一到图谱组件 ID 与运行状态。

纯函数，不发请求、不碰数据库 —— 因此可以完整单测（用 mock apiserver 的响应体当输入）。
"""
from __future__ import annotations

from .client import ResourceNotFound

# 组件 ID 与采集路径：一个组件一条路径，缺哪条就对应哪个槽位 not_detected
COMPONENT_PATHS = {
    "apiserver":      "/version",
    "etcd":           "/api/v1/namespaces",        # etcd 不直接暴露，用 API 可用性反推
    "scheduler":      "/api/v1/namespaces",
    "kcm":            "/api/v1/namespaces",
    "coredns":        "/api/v1/namespaces/kube-system/services",
    "kubelet":        "/api/v1/nodes",
    "kube-proxy":     "/api/v1/nodes",
    "cni":            "/api/v1/nodes",
    "runtime":        "/api/v1/nodes",
    "node":           "/api/v1/nodes",
    "service":        "/api/v1/services",
    "endpointslice":  "/apis/discovery.k8s.io/v1/endpointslices",
    "netpol":         "/apis/networking.k8s.io/v1/networkpolicies",
    "pod":            "/api/v1/pods",
    "deployment":     "/apis/apps/v1/deployments",
    "statefulset":    "/apis/apps/v1/statefulsets",
    "daemonset":      "/apis/apps/v1/daemonsets",
    "job":            "/apis/batch/v1/jobs",
    "hpa":            "/apis/autoscaling/v2/horizontalpodautoscalers",
    "pvc":            "/api/v1/persistentvolumeclaims",
    "pv":             "/api/v1/persistentvolumes",
    "storageclass":   "/apis/storage.k8s.io/v1/storageclasses",
    "csidriver":      "/apis/storage.k8s.io/v1/csidrivers",
    "rbac":           "/apis/rbac.authorization.k8s.io/v1/clusterroles",
    "sa":             "/api/v1/serviceaccounts",
    "secret":         "/api/v1/secrets",
    "psa":            "/api/v1/namespaces",
    "ingress":        "/apis/networking.k8s.io/v1/ingresses",
    "gateway":        "/apis/gateway.networking.k8s.io/v1/gateways",
    "httproute":      "/apis/gateway.networking.k8s.io/v1/httproutes",
    "prometheus":     "/api/v1/namespaces",
    "metricsserver":  "/apis/metrics.k8s.io/v1/nodes",
    "logs":           "/api/v1/namespaces",
}

# 这些组件没有独立 API 路径，靠其它信号推断
DERIVED_ONLY = {"etcd", "scheduler", "kcm", "admission", "ccm", "gatewayclass", "overlay", "envoy", "hubble", "vap"}


def _ready(node: dict) -> bool:
    for c in node.get("status", {}).get("conditions", []):
        if c.get("type") == "Ready":
            return c.get("status") == "True"
    return False


def summarize_nodes(items: list[dict]) -> dict:
    total = len(items)
    ready = sum(1 for n in items if _ready(n))
    not_ready = [
        {
            "name": n["metadata"]["name"],
            "reason": next(
                (c.get("reason") or c.get("message") or "Unknown"
                 for c in n.get("status", {}).get("conditions", []) if c.get("type") == "Ready" and c.get("status") != "True"),
                "Unknown",
            ),
            "kubelet": n.get("status", {}).get("nodeInfo", {}).get("kubeletVersion", ""),
            "runtime": n.get("status", {}).get("nodeInfo", {}).get("containerRuntimeVersion", ""),
        }
        for n in items if not _ready(n)
    ]
    return {"total": total, "ready": ready, "not_ready": ready - total if False else total - ready, "items": not_ready}


def summarize_pods(items: list[dict]) -> dict:
    buckets = {"Running": 0, "Pending": 0, "Failed": 0, "Succeeded": 0, "Unknown": 0}
    problems = []
    for p in items:
        phase = p.get("status", {}).get("phase", "Unknown")
        buckets[phase if phase in buckets else "Unknown"] += 1
        for cs in p.get("status", {}).get("containerStatuses", []):
            waiting = cs.get("state", {}).get("waiting", {})
            if waiting:
                problems.append({
                    "name": f"{p['metadata']['namespace']}/{p['metadata']['name']}",
                    "reason": waiting.get("reason", "Unknown"),
                    "message": (waiting.get("message") or "")[:120],
                })
    return {"total": len(items), "by_phase": buckets, "problems": problems[:20]}


def summarize_workloads(items: list[dict], kind: str) -> dict:
    total = len(items)
    desired = sum(d.get("spec", {}).get("replicas", 0) or 0 for d in items)
    ready = sum(d.get("status", {}).get("readyReplicas", 0) or 0 for d in items)
    degraded = [
        {"name": d["metadata"]["name"], "namespace": d["metadata"]["namespace"],
         "desired": d.get("spec", {}).get("replicas", 0), "ready": d.get("status", {}).get("readyReplicas", 0)}
        for d in items if (d.get("status", {}).get("readyReplicas", 0) or 0) < (d.get("spec", {}).get("replicas", 0) or 0)
    ]
    return {"kind": kind, "total": total, "desired": desired, "ready": ready, "degraded": degraded[:10]}


def summarize_services(items: list[dict]) -> dict:
    by_type: dict[str, int] = {}
    for s in items:
        t = s.get("spec", {}).get("type", "ClusterIP")
        by_type[t] = by_type.get(t, 0) + 1
    return {"total": len(items), "by_type": by_type}


def detect_cni(items: list[dict]) -> dict:
    """通过 Node 上运行的 DaemonSet 名称猜 CNI（kube-proxy 一定在）。"""
    names = {d["metadata"]["name"] for d in items}
    mapping = [
        ("cilium", "Cilium"),
        ("calico", "Calico"),
        ("flannel", "Flannel"),
        ("weave", "Weave Net"),
    ]
    for key, label in mapping:
        if any(key in n for n in names):
            return {"name": label, "evidence": sorted(n for n in names if key in n)[:3]}
    return {"name": "未识别", "evidence": []}


def detect_logging_agent(items: list[dict]) -> dict:
    names = {d["metadata"]["name"] for d in items}
    for key in ("fluent-bit", "fluentbit", "filebeat", "vector", "promtail", "loki"):
        hit = [n for n in names if key in n]
        if hit:
            return {"name": key, "evidence": hit[:3]}
    return {"name": "未识别", "evidence": []}


def summarize_ingresses(items: list[dict]) -> dict:
    hosts = set()
    for ing in items:
        for rule in ing.get("spec", {}).get("rules", []) or []:
            host = rule.get("host")
            if host:
                hosts.add(host)
    return {"total": len(items), "hosts": sorted(hosts)[:20]}


def summarize_networkpolicies(items: list[dict]) -> dict:
    return {
        "total": len(items),
        "namespaces": sorted({i["metadata"]["namespace"] for i in items})[:20],
    }


def summarize_pvcs(items: list[dict]) -> dict:
    bound = sum(1 for p in items if p.get("status", {}).get("phase") == "Bound")
    pending = [
        {"name": p["metadata"]["name"], "namespace": p["metadata"]["namespace"]}
        for p in items if p.get("status", {}).get("phase") != "Bound"
    ]
    return {"total": len(items), "bound": bound, "pending": pending[:10]}


def summarize_storageclasses(items: list[dict]) -> dict:
    default = [s["metadata"]["name"] for s in items
               if s.get("metadata", {}).get("annotations", {})
               .get("storageclass.kubernetes.io/is-default-class") == "true"]
    return {"total": len(items), "default": default}


def summarize_namespaces(items: list[dict]) -> dict:
    psa = {}
    for n in items:
        ann = n.get("metadata", {}).get("annotations", {})
        enforce = ann.get("pod-security.kubernetes.io/enforce")
        if enforce:
            psa[n["metadata"]["name"]] = enforce
    return {"total": len(items), "psa_enforced": psa}


def summarize_secrets(items: list[dict]) -> dict:
    return {"total": len(items)}


def summarize_serviceaccounts(items: list[dict]) -> dict:
    return {"total": len(items)}


def summarize_clusterroles(items: list[dict]) -> dict:
    return {"total": len(items)}


def summarize_endpointslices(items: list[dict]) -> dict:
    with_endpoints = sum(1 for e in items if e.get("endpoints"))
    return {"total": len(items), "with_endpoints": with_endpoints, "empty": len(items) - with_endpoints}


def summarize_metrics_nodes(items: list[dict]) -> dict:
    return {"total": len(items), "sample": items[:1]}


def version_of(version_obj: dict) -> str:
    return version_obj.get("gitVersion", "unknown")
