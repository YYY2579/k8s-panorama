"""集群接入模块测试：mapper 纯函数 + client 只读边界 + 路由降级。

mapper 用 mock apiserver 同结构的 JSON 做输入，不起真实 HTTP 服务；
client 与路由用一个本地假 apiserver（http.server）验证真实请求路径。
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.cluster import mapper
from app.cluster.client import ReadOnlyKubeClient
from app.cluster.errors import ClusterUnreachable
from app.cluster.snapshot import build_components, collect


# ---------------- fixture：本地假 apiserver ----------------
NODES = {"items": [
    {"metadata": {"name": "n1"}, "status": {"conditions": [{"type": "Ready", "status": "True"}],
     "nodeInfo": {"kubeletVersion": "v1.29.3", "containerRuntimeVersion": "containerd://1.7"}}},
    {"metadata": {"name": "n2"}, "status": {"conditions": [{"type": "Ready", "status": "False",
     "reason": "KubeletNotReady"}], "nodeInfo": {"kubeletVersion": "v1.29.3"}}},
]}
PODS = {"items": [
    {"metadata": {"name": "p1", "namespace": "default"}, "status": {"phase": "Running"}},
    {"metadata": {"name": "p2", "namespace": "default"}, "status": {"phase": "Pending"}},
    {"metadata": {"name": "p3", "namespace": "default"}, "status": {"phase": "Running",
     "containerStatuses": [{"name": "c", "state": {"waiting": {"reason": "CrashLoopBackOff"}}}]}},
]}
DAEMONSETS = {"items": [{"metadata": {"name": "cilium-agent"}}, {"metadata": {"name": "fluent-bit"}}]}
INGRESSES = {"items": [{"metadata": {"name": "web"},
                        "spec": {"rules": [{"host": "a.com"}, {"host": "b.com"}]}}]}
DEPLOYMENTS = {"items": [
    {"metadata": {"name": "api", "namespace": "default"}, "spec": {"replicas": 3},
     "status": {"readyReplicas": 2}},
]}


class _FakeAPI(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _json(self, code, payload):
        raw = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        p = self.path.split("?")[0]
        table = {
            "/version": {"gitVersion": "v1.29.3"},
            "/api/v1/nodes": NODES,
            "/api/v1/pods": PODS,
            "/apis/apps/v1/daemonsets": DAEMONSETS,
            "/apis/networking.k8s.io/v1/ingresses": INGRESSES,
            "/apis/apps/v1/deployments": DEPLOYMENTS,
            "/api/v1/namespaces": {"items": []},
        }
        if p in table:
            self._json(200, table[p])
        elif p.startswith("/apis/gateway.networking.k8s.io/"):
            self._json(404, {"kind": "Status", "status": "Failure", "code": 404})
        else:
            self._json(404, {"kind": "Status", "code": 404})


@pytest.fixture(scope="module")
def fake_api():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _FakeAPI)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


# ---------------- mapper 纯函数 ----------------


def test_summarize_nodes_ready_ratio():
    s = mapper.summarize_nodes(NODES["items"])
    assert s["total"] == 2 and s["ready"] == 1 and s["not_ready"] == 1
    assert s["items"][0]["name"] == "n2"
    assert s["items"][0]["reason"] == "KubeletNotReady"


def test_summarize_pods_phases_and_problems():
    s = mapper.summarize_pods(PODS["items"])
    assert s["total"] == 3
    assert s["by_phase"]["Running"] == 2 and s["by_phase"]["Pending"] == 1
    assert s["problems"][0]["reason"] == "CrashLoopBackOff"
    assert s["problems"][0]["name"] == "default/p3"


def test_summarize_workloads_degraded():
    s = mapper.summarize_workloads(DEPLOYMENTS["items"], "Deployment")
    assert s["desired"] == 3 and s["ready"] == 2
    assert s["degraded"][0]["name"] == "api"


def test_summarize_ingresses_hosts():
    """回归：曾因把 rule dict 放进 set 导致 unhashable type: dict。"""
    s = mapper.summarize_ingresses(INGRESSES["items"])
    assert s["total"] == 1
    assert s["hosts"] == ["a.com", "b.com"]


def test_summarize_ingresses_empty_rules():
    s = mapper.summarize_ingresses([{"metadata": {"name": "x"}, "spec": {}}])
    assert s == {"total": 1, "hosts": []}


def test_detect_cni():
    assert mapper.detect_cni(DAEMONSETS["items"])["name"] == "Cilium"
    assert mapper.detect_cni([{"metadata": {"name": "kube-proxy"}}])["name"] == "未识别"


def test_detect_logging_agent():
    assert mapper.detect_logging_agent(DAEMONSETS["items"])["name"] == "fluent-bit"


def test_summarize_pvcs():
    s = mapper.summarize_pvcs([
        {"metadata": {"name": "a", "namespace": "d"}, "status": {"phase": "Bound"}},
        {"metadata": {"name": "b", "namespace": "d"}, "status": {"phase": "Pending"}},
    ])
    assert s["bound"] == 1 and len(s["pending"]) == 1


def test_summarize_storageclasses_default():
    s = mapper.summarize_storageclasses([
        {"metadata": {"name": "nfs", "annotations": {"storageclass.kubernetes.io/is-default-class": "true"}}},
        {"metadata": {"name": "local"}},
    ])
    assert s["default"] == ["nfs"]


def test_summarize_namespaces_psa():
    s = mapper.summarize_namespaces([
        {"metadata": {"name": "prod", "annotations": {"pod-security.kubernetes.io/enforce": "restricted"}}},
        {"metadata": {"name": "dev"}},
    ])
    assert s["psa_enforced"] == {"prod": "restricted"}


def test_summarize_endpointslices():
    s = mapper.summarize_endpointslices([
        {"endpoints": [{"addresses": ["1.2.3.4"]}]}, {"endpoints": []},
    ])
    assert s["total"] == 2 and s["with_endpoints"] == 1 and s["empty"] == 1


# ---------------- client 只读边界 ----------------


def test_client_get_ok(fake_api):
    c = ReadOnlyKubeClient(api_server=fake_api, timeout=5)
    d = c.get("/version")
    assert d["gitVersion"] == "v1.29.3"


def test_client_404_raises_resource_not_found(fake_api):
    from app.cluster.client import ResourceNotFound
    c = ReadOnlyKubeClient(api_server=fake_api, timeout=5)
    with pytest.raises(ResourceNotFound):
        c.get("/apis/gateway.networking.k8s.io/v1/gateways")


def test_client_unreachable_raises_cluster_error():
    """指向一个没人监听的端口，必须转成 ClusterUnreachable 而不是裸异常。"""
    c = ReadOnlyKubeClient(api_server="http://127.0.0.1:1", timeout=2)
    with pytest.raises(ClusterUnreachable):
        c.get("/version")


def test_client_has_no_write_methods():
    """代码里不存在写方法（不是"不调用"）。"""
    for m in ("post", "put", "patch", "delete", "create", "update"):
        assert not hasattr(ReadOnlyKubeClient, m), f"不应存在 {m} 方法"


def test_client_allowed_methods_constant():
    from app.cluster.client import ALLOWED_METHODS
    assert ALLOWED_METHODS == ("GET",)


# ---------------- snapshot 汇总 ----------------


def test_build_components_from_fake_api(fake_api):
    c = ReadOnlyKubeClient(api_server=fake_api, timeout=5)
    snap = collect(c)
    comps = {x["component_id"]: x for x in build_components(snap)}

    assert comps["apiserver"]["state"] == "present"
    assert comps["apiserver"]["detail"]["version"] == "v1.29.3"
    #  mock 里 node-2 NotReady → node 应为 unhealthy
    assert comps["node"]["state"] == "unhealthy"
    assert comps["node"]["detail"]["not_ready"] == 1
    #  mock 里有 Pending/CrashLoop → pod 应为 unhealthy
    assert comps["pod"]["state"] == "unhealthy"
    assert comps["pod"]["detail"]["by_phase"]["Pending"] == 1
    #  deployment 3 期望 2 就绪
    assert comps["deployment"]["state"] == "unhealthy"
    #  Gateway API 404 → not_detected
    assert comps["gateway"]["state"] == "not_detected"
    assert comps["httproute"]["state"] == "not_detected"
    #  CNI 与日志 agent 从 DaemonSet 识别
    assert comps["cni"]["detail"]["name"] == "Cilium"
    assert comps["logs"]["detail"]["name"] == "fluent-bit"
    #  ingress hosts 曾因 dict 进 set 崩溃，现在应正常
    assert comps["ingress"]["detail"]["hosts"] == ["a.com", "b.com"]


def test_build_components_only_four_states(fake_api):
    """对外只暴露设计约定的四态。"""
    c = ReadOnlyKubeClient(api_server=fake_api, timeout=5)
    comps = build_components(collect(c))
    allowed = {"present", "unhealthy", "not_detected", "unknown"}
    assert {x["state"] for x in comps} <= allowed
    assert len(comps) >= 30


def test_single_component_failure_does_not_break_others():
    """某个组件解析失败只把自己标 unknown，不影响其他组件。"""
    snap = {"raw": {"/version": {"data": {"gitVersion": "v1.29.3"}, "error": None}}, "elapsed_ms": 1}
    comps = {x["component_id"]: x for x in build_components(snap)}
    assert comps["apiserver"]["state"] == "present"
    assert comps["apiserver"]["detail"]["version"] == "v1.29.3"
    assert comps["pod"]["state"] == "unknown"        # 没数据 → unknown，不是崩溃
    assert comps["gateway"]["state"] == "unknown"    # 没有 404 证据时也是 unknown，不是崩溃


# ---------------- 路由降级 ----------------


def test_cluster_status_requires_login(client):
    assert client.get("/api/cluster/status").status_code == 401


def test_cluster_status_configured(admin_client, monkeypatch, fake_api):
    """配置了可达集群 → 200 且 degraded=False。"""
    monkeypatch.setenv("ATLAS_K8S_API", fake_api)
    from app.cluster import router as r
    r._cache.invalidate()
    r._last_good.value = None

    resp = admin_client.get("/api/cluster/status")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["degraded"] is False
    assert body["version"] == "v1.29.3"
    ids = {c["component_id"] for c in body["components"]}
    assert {"apiserver", "node", "pod", "gateway"} <= ids


def test_cluster_status_unreachable_returns_503(admin_client, monkeypatch):
    """连不上 → 503 + degraded，不是 500。"""
    monkeypatch.setenv("ATLAS_K8S_API", "http://127.0.0.1:1")
    from app.cluster import router as r
    r._cache.invalidate()
    r._last_good.value = None          # 清掉上一次成功快照，否则会走 stale 分支返回 200

    resp = admin_client.get("/api/cluster/status")
    assert resp.status_code == 503
    body = resp.json()["detail"]        # FastAPI 把 HTTPException.detail 包在 detail 里
    assert body["degraded"] is True
    assert body["reason"] == "unreachable"
    assert "降级" in body["hint"] and "不受影响" in body["hint"]


def test_cluster_status_not_configured_returns_503(admin_client, monkeypatch):
    monkeypatch.delenv("ATLAS_K8S_API", raising=False)
    monkeypatch.setenv("ATLAS_KUBECONFIG", "/nonexistent/kubeconfig")
    from app.cluster import router as r
    r._cache.invalidate()
    r._last_good.value = None

    resp = admin_client.get("/api/cluster/status")
    assert resp.status_code == 503
    assert resp.json()["detail"]["reason"] == "not_configured"


def test_cluster_stale_snapshot_when_unreachable(admin_client, monkeypatch, fake_api):
    """先成功一次，再断开 → 返回上一次快照并标 stale。"""
    from app.cluster import router as r
    monkeypatch.setenv("ATLAS_K8S_API", fake_api)
    r._cache.invalidate(); r._last_good.value = None
    assert admin_client.get("/api/cluster/status").status_code == 200

    monkeypatch.setenv("ATLAS_K8S_API", "http://127.0.0.1:1")
    r._cache.invalidate()
    resp = admin_client.get("/api/cluster/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["degraded"] is True and body["stale"] is True
    assert body["components"]


def test_cluster_nodes_endpoint(admin_client, monkeypatch, fake_api):
    monkeypatch.setenv("ATLAS_K8S_API", fake_api)
    from app.cluster import router as r
    r._cache.invalidate()
    resp = admin_client.get("/api/cluster/nodes")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2 and body["not_ready"] == 1


def test_cluster_does_not_write(admin_client, monkeypatch, fake_api):
    """集群接口只读：不应产生任何 atlas 侧写操作。"""
    monkeypatch.setenv("ATLAS_K8S_API", fake_api)
    from app.cluster import router as r
    r._cache.invalidate()
    before = admin_client.get("/api/health").json()["counts"]
    admin_client.get("/api/cluster/status")
    admin_client.get("/api/cluster/components")
    after = admin_client.get("/api/health").json()["counts"]
    for key in ("nodes", "edges", "notes", "sops", "yamls"):
        assert before[key] == after[key], f"{key} 被集群接口改动了"
