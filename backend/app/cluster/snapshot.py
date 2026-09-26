"""集群快照：采集 + 汇总 + 派生指标。

采集策略：每个组件一条 API 路径，404 记 not_detected，异常记 unknown，
成功则按 mapper 的 summarize_* 生成详情。

健壮性：每个组件的汇总都单独隔离 —— 真实集群的字段可能缺失或类型不符，
单个组件解析失败只把自己标成 unknown，不会让整个集群视图 500。
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from .client import ReadOnlyKubeClient, ResourceNotFound
from .errors import ClusterError
from . import mapper

MAX_WORKERS = 6


def collect(client: ReadOnlyKubeClient) -> dict:
    """并发采集全部组件路径，返回结构化快照。

    单条路径失败只记 error（对应组件标 unknown/not_detected），不影响其他；
    但**所有**路径都失败说明集群整体不可达，此时抛 ClusterUnreachable，
    让路由层走降级逻辑（503 或返回上一次快照）。
    """
    started = time.monotonic()

    def fetch(path: str):
        try:
            return path, client.get(path), None
        except ResourceNotFound:
            return path, None, "not_found"
        except ClusterError as e:
            return path, None, e.reason

    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for path, data, err in pool.map(fetch, sorted(set(mapper.COMPONENT_PATHS.values()))):
            results[path] = {"data": data, "error": err}

    # 全部不可达（既没有成功，也没有"资源不存在"这类有意义的 404）→ 视为集群不可达
    errors = [v["error"] for v in results.values()]
    if errors and all(e not in (None, "not_found") for e in errors):
        from .errors import ClusterUnreachable
        raise ClusterUnreachable(
            f"全部 {len(results)} 个接口均不可达（如 {errors[0]}），请检查集群地址与凭证"
        )

    elapsed = round((time.monotonic() - started) * 1000, 1)
    return {"raw": results, "elapsed_ms": elapsed}


def build_components(snapshot: dict) -> list[dict]:
    """把原始响应转成「组件 ID → 状态」列表。"""
    raw = snapshot["raw"]
    out: list[dict] = []

    def entry(path: str) -> tuple[str, dict]:
        """返回 (state, data)。state ∈ present / not_found / unknown。"""
        e = raw.get(path)
        if not e:
            return "unknown", {}
        if e["error"]:
            return ("not_found" if e["error"] == "not_found" else "unknown"), {}
        return "present", e["data"] or {}

    def safe(cid: str, fn):
        """单个组件的汇总隔离：失败只影响自己。"""
        try:
            return fn()
        except Exception as exc:                      # noqa: BLE001 —— 刻意兜住，保证局部失败不扩散
            return _c(cid, "unknown", {"error": f"{type(exc).__name__}: {exc}"[:150]})

    # ---------- 控制面 ----------
    st, ver = entry("/version")
    out.append(safe("apiserver", lambda: _c(
        "apiserver", st,
        {"version": mapper.version_of(ver) if st == "present" else ""})))

    st, _ = entry("/api/v1/namespaces")
    for cid, note in [
        ("etcd", "etcd 不直接暴露，以 API 可用性反推"),
        ("scheduler", "控制面组件，以 API 可用性反推"),
        ("kcm", "控制面组件，以 API 可用性反推"),
    ]:
        out.append(safe(cid, lambda c=cid, n=note: _c(c, st, {"note": n})))

    st, svc = entry("/api/v1/namespaces/kube-system/services")
    dns = [s for s in svc.get("items", []) if s.get("metadata", {}).get("name") == "kube-dns"] if st == "present" else []
    out.append(safe("coredns", lambda: _c(
        "coredns", "present" if dns else ("not_detected" if st == "present" else st),
        {"clusterIP": dns[0].get("spec", {}).get("clusterIP") if dns else ""})))

    # ---------- 节点与网络底座 ----------
    st, nodes = entry("/api/v1/nodes")
    node_items = nodes.get("items", []) if st == "present" else []
    out.append(safe("node", lambda: _c("node", st, mapper.summarize_nodes(node_items),
                                       unhealthy=bool(node_items) and
                                       mapper.summarize_nodes(node_items)["not_ready"] > 0)))
    out.append(safe("kubelet", lambda: _c(
        "kubelet", st,
        {"versions": sorted({n.get("status", {}).get("nodeInfo", {}).get("kubeletVersion", "")
                             for n in node_items if n.get("status", {}).get("nodeInfo", {}).get("kubeletVersion")})})))
    out.append(safe("runtime", lambda: _c(
        "runtime", st,
        {"runtimes": sorted({n.get("status", {}).get("nodeInfo", {}).get("containerRuntimeVersion", "")
                             for n in node_items if n.get("status", {}).get("nodeInfo", {}).get("containerRuntimeVersion")})})))
    out.append(safe("kube-proxy", lambda: _c("kube-proxy", st, {})))

    st, ds = entry("/apis/apps/v1/daemonsets")
    ds_items = ds.get("items", []) if st == "present" else []
    out.append(safe("cni", lambda: _c("cni", st, mapper.detect_cni(ds_items))))
    out.append(safe("logs", lambda: _c("logs", st, mapper.detect_logging_agent(ds_items))))

    st, svcs = entry("/api/v1/services")
    out.append(safe("service", lambda: _c("service", st,
                                          mapper.summarize_services(svcs.get("items", [])) if st == "present" else {})))

    st, eps = entry("/apis/discovery.k8s.io/v1/endpointslices")
    out.append(safe("endpointslice", lambda: _c(
        "endpointslice", st,
        mapper.summarize_endpointslices(eps.get("items", [])) if st == "present" else {})))

    st, np = entry("/apis/networking.k8s.io/v1/networkpolicies")
    out.append(safe("netpol", lambda: _c(
        "netpol", st,
        mapper.summarize_networkpolicies(np.get("items", [])) if st == "present" else {})))

    # ---------- 工作负载 ----------
    st, pods = entry("/api/v1/pods")
    pod_sum = mapper.summarize_pods(pods.get("items", [])) if st == "present" else {}
    out.append(safe("pod", lambda: _c("pod", st, pod_sum, unhealthy=bool(pod_sum.get("problems")))))

    for cid, path, kind in [
        ("deployment", "/apis/apps/v1/deployments", "Deployment"),
        ("statefulset", "/apis/apps/v1/statefulsets", "StatefulSet"),
    ]:
        st, items = entry(path)
        w = mapper.summarize_workloads(items.get("items", []), kind) if st == "present" else {}
        out.append(safe(cid, lambda c=cid, s=st, ww=w: _c(c, s, ww, unhealthy=bool(ww.get("degraded")))))

    st, jobs = entry("/apis/batch/v1/jobs")
    out.append(safe("job", lambda: _c("job", st, {"total": len(jobs.get("items", []))} if st == "present" else {})))

    st, hpa = entry("/apis/autoscaling/v2/horizontalpodautoscalers")
    out.append(safe("hpa", lambda: _c("hpa", st, {"total": len(hpa.get("items", []))} if st == "present" else {})))

    # ---------- 存储与安全 ----------
    st, pvc = entry("/api/v1/persistentvolumeclaims")
    pvc_sum = mapper.summarize_pvcs(pvc.get("items", [])) if st == "present" else {}
    out.append(safe("pvc", lambda: _c("pvc", st, pvc_sum, unhealthy=bool(pvc_sum.get("pending")))))

    st, pv = entry("/api/v1/persistentvolumes")
    out.append(safe("pv", lambda: _c("pv", st, {"total": len(pv.get("items", []))} if st == "present" else {})))

    st, sc = entry("/apis/storage.k8s.io/v1/storageclasses")
    out.append(safe("storageclass", lambda: _c(
        "storageclass", st,
        mapper.summarize_storageclasses(sc.get("items", [])) if st == "present" else {})))

    st, csi = entry("/apis/storage.k8s.io/v1/csidrivers")
    out.append(safe("csidriver", lambda: _c("csidriver", st, {"total": len(csi.get("items", []))} if st == "present" else {})))

    st, cr = entry("/apis/rbac.authorization.k8s.io/v1/clusterroles")
    out.append(safe("rbac", lambda: _c(
        "rbac", st, mapper.summarize_clusterroles(cr.get("items", [])) if st == "present" else {})))

    st, sa = entry("/api/v1/serviceaccounts")
    out.append(safe("sa", lambda: _c(
        "sa", st, mapper.summarize_serviceaccounts(sa.get("items", [])) if st == "present" else {})))

    st, sec = entry("/api/v1/secrets")
    out.append(safe("secret", lambda: _c(
        "secret", st, mapper.summarize_secrets(sec.get("items", [])) if st == "present" else {})))

    st, ns = entry("/api/v1/namespaces")
    out.append(safe("psa", lambda: _c(
        "psa", st, mapper.summarize_namespaces(ns.get("items", [])) if st == "present" else {})))

    # ---------- 入口 ----------
    st, ing = entry("/apis/networking.k8s.io/v1/ingresses")
    out.append(safe("ingress", lambda: _c(
        "ingress", st, mapper.summarize_ingresses(ing.get("items", [])) if st == "present" else {})))

    st, gw = entry("/apis/gateway.networking.k8s.io/v1/gateways")
    out.append(safe("gateway", lambda: _c("gateway", st, {"total": len(gw.get("items", []))} if st == "present" else {})))

    st, hr = entry("/apis/gateway.networking.k8s.io/v1/httproutes")
    out.append(safe("httproute", lambda: _c("httproute", st, {"total": len(hr.get("items", []))} if st == "present" else {})))

    # ---------- 可观测 ----------
    st, mn = entry("/apis/metrics.k8s.io/v1/nodes")
    out.append(safe("metricsserver", lambda: _c(
        "metricsserver", st, mapper.summarize_metrics_nodes(mn.get("items", [])) if st == "present" else {})))

    # ---------- 无独立探测路径 ----------
    for cid in ("admission", "ccm", "gatewayclass", "overlay", "envoy", "hubble", "vap", "prometheus"):
        out.append(_c(cid, "unknown", {"note": "无独立探测路径"}))

    return out


def _c(cid: str, state: str, detail: dict, unhealthy: bool = False) -> dict:
    """构造一条组件标注。

    对外只暴露四种状态：present / unhealthy / not_detected / unknown
    （设计文档约定的槽位四态）。内部的 not_found 在这里归一成 not_detected。
    """
    if state == "not_found":
        state = "not_detected"
    if unhealthy and state == "present":
        state = "unhealthy"
    return {"component_id": cid, "state": state, "detail": detail}
