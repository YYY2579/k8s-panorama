#!/usr/bin/env python
"""模拟 kube-apiserver：返回真实结构的 K8s JSON，用于在没有集群的环境下验证接入链路。

包含刻意制造的异常，便于验证状态判定：
  - node-2 为 NotReady
  - pod web-0 处于 Pending
  - pod api-7d9f-xyz 容器 CrashLoopBackOff
  - Gateway API 相关路径返回 404（模拟集群未安装）
  - DaemonSet 里放 cilium-agent（验证 CNI 探测）

用法：
    python scripts/mock_k8s.py [--port 18081]
"""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = {"major": "1", "minor": "29", "gitVersion": "v1.29.3", "platform": "linux/amd64"}

NODES = {
    "kind": "NodeList",
    "apiVersion": "v1",
    "items": [
        {
            "metadata": {"name": "master-1"},
            "status": {
                "conditions": [{"type": "Ready", "status": "True"}],
                "nodeInfo": {"kubeletVersion": "v1.29.3", "containerRuntimeVersion": "containerd://1.7.11"},
            },
        },
        {
            "metadata": {"name": "node-2"},
            "status": {
                "conditions": [{"type": "Ready", "status": "False", "reason": "KubeletNotReady",
                                "message": "container runtime is down"}],
                "nodeInfo": {"kubeletVersion": "v1.29.3", "containerRuntimeVersion": "containerd://1.7.11"},
            },
        },
    ],
}

PODS = {
    "kind": "PodList",
    "apiVersion": "v1",
    "items": [
        {"metadata": {"name": "api-7d9f-abcde", "namespace": "default"},
         "status": {"phase": "Running",
                    "containerStatuses": [{"name": "app", "ready": True,
                                           "restartCount": 0, "state": {"running": {"startedAt": "2026-09-26T01:00:00Z"}}}]}},
        {"metadata": {"name": "web-0", "namespace": "default"},
         "status": {"phase": "Pending",
                    "containerStatuses": [{"name": "nginx", "ready": False, "restartCount": 0,
                                           "state": {"waiting": {"reason": "ContainerCreating",
                                                                 "message": "failed to mount volume"}}}]}},
        {"metadata": {"name": "api-7d9f-xyz", "namespace": "default"},
         "status": {"phase": "Running",
                    "containerStatuses": [{"name": "app", "ready": False, "restartCount": 7,
                                           "state": {"waiting": {"reason": "CrashLoopBackOff",
                                                                 "message": "back-off 5m0s restarting failed container"}}}]}},
    ],
}

SERVICES = {"kind": "ServiceList", "apiVersion": "v1", "items": [
    {"metadata": {"name": "kubernetes", "namespace": "default"},
     "spec": {"type": "ClusterIP", "clusterIP": "10.96.0.1"}},
    {"metadata": {"name": "api", "namespace": "default"},
     "spec": {"type": "ClusterIP", "clusterIP": "10.96.12.34"}},
    {"metadata": {"name": "web-lb", "namespace": "default"},
     "spec": {"type": "LoadBalancer", "clusterIP": "10.96.55.10"}},
]}

NAMESPACES = {"kind": "NamespaceList", "apiVersion": "v1", "items": [
    {"metadata": {"name": "default"}},
    {"metadata": {"name": "kube-system",
                  "annotations": {"pod-security.kubernetes.io/enforce": "privileged"}}},
    {"metadata": {"name": "prod",
                  "annotations": {"pod-security.kubernetes.io/enforce": "restricted"}}},
]}

KUBE_DNS = {"kind": "ServiceList", "apiVersion": "v1", "items": [
    {"metadata": {"name": "kube-dns", "namespace": "kube-system"},
     "spec": {"type": "ClusterIP", "clusterIP": "10.96.0.10"}},
]}

ENDPOINTSLICES = {"kind": "EndpointSliceList", "apiVersion": "discovery.k8s.io/v1", "items": [
    {"metadata": {"name": "api-abcde", "namespace": "default"},
     "endpoints": [{"addresses": ["10.244.1.5"], "conditions": {"ready": True}}]},
    {"metadata": {"name": "web-empty", "namespace": "default"}, "endpoints": []},
]}

NETWORKPOLICIES = {"kind": "NetworkPolicyList", "apiVersion": "networking.k8s.io/v1", "items": [
    {"metadata": {"name": "default-deny", "namespace": "prod"}},
]}

DEPLOYMENTS = {"kind": "DeploymentList", "apiVersion": "apps/v1", "items": [
    {"metadata": {"name": "api", "namespace": "default"}, "spec": {"replicas": 3},
     "status": {"readyReplicas": 2}},
    {"metadata": {"name": "web", "namespace": "default"}, "spec": {"replicas": 2},
     "status": {"readyReplicas": 2}},
]}

STATEFULSETS = {"kind": "StatefulSetList", "apiVersion": "apps/v1", "items": [
    {"metadata": {"name": "db", "namespace": "default"}, "spec": {"replicas": 1},
     "status": {"readyReplicas": 1}},
]}

DAEMONSETS = {"kind": "DaemonSetList", "apiVersion": "apps/v1", "items": [
    {"metadata": {"name": "cilium-agent", "namespace": "kube-system"}},
    {"metadata": {"name": "cilium-envoy", "namespace": "kube-system"}},
    {"metadata": {"name": "fluent-bit", "namespace": "logging"}},
    {"metadata": {"name": "node-exporter", "namespace": "monitoring"}},
]}

JOBS = {"kind": "JobList", "apiVersion": "batch/v1", "items": [
    {"metadata": {"name": "migrate-20260926", "namespace": "default"}},
]}

HPAS = {"kind": "HorizontalPodAutoscalerList", "apiVersion": "autoscaling/v2", "items": [
    {"metadata": {"name": "api", "namespace": "default"}, "spec": {"minReplicas": 2, "maxReplicas": 10}},
]}

PVCS = {"kind": "PersistentVolumeClaimList", "apiVersion": "v1", "items": [
    {"metadata": {"name": "data-db-0", "namespace": "default"}, "status": {"phase": "Bound"}},
    {"metadata": {"name": "data-web-0", "namespace": "default"}, "status": {"phase": "Pending"}},
]}

PVS = {"kind": "PersistentVolumeList", "apiVersion": "v1", "items": [
    {"metadata": {"name": "pv-nfs-01"}, "spec": {"capacity": {"storage": "50Gi"}}},
]}

STORAGECLASSES = {"kind": "StorageClassList", "apiVersion": "storage.k8s.io/v1", "items": [
    {"metadata": {"name": "nfs-client",
                  "annotations": {"storageclass.kubernetes.io/is-default-class": "true"}}},
    {"metadata": {"name": "local-path"}},
]}

CSIDRIVERS = {"kind": "CSIDriverList", "apiVersion": "storage.k8s.io/v1", "items": [
    {"metadata": {"name": "nfs.csi.k8s.io"}},
]}

CLUSTERROLES = {"kind": "ClusterRoleList", "apiVersion": "rbac.authorization.k8s.io/v1", "items": [
    {"metadata": {"name": "cluster-admin"}}, {"metadata": {"name": "view"}},
    {"metadata": {"name": "edit"}}, {"metadata": {"name": "system:controller:deployment-controller"}},
]}

SERVICEACCOUNTS = {"kind": "ServiceAccountList", "apiVersion": "v1", "items": [
    {"metadata": {"name": "default", "namespace": "default"}},
    {"metadata": {"name": "api", "namespace": "default"}},
]}

SECRETS = {"kind": "SecretList", "apiVersion": "v1", "items": [
    {"metadata": {"name": "api-tls", "namespace": "default"}},
    {"metadata": {"name": "regcred", "namespace": "default"}},
]}

INGRESSES = {"kind": "IngressList", "apiVersion": "networking.k8s.io/v1", "items": [
    {"metadata": {"name": "web", "namespace": "default"},
     "spec": {"rules": [{"host": "app.example.com"}, {"host": "api.example.com"}]}},
]}

METRICS_NODES = {"kind": "NodeMetricsList", "apiVersion": "metrics.k8s.io/v1", "items": [
    {"metadata": {"name": "master-1"}, "timestamp": "2026-09-26T01:00:00Z",
     "usage": {"cpu": "120m", "memory": "1200Mi"}},
]}

ROUTES = {
    "/version": VERSION,
    "/healthz": {"status": "ok"},
    "/api/v1/nodes": NODES,
    "/api/v1/pods": PODS,
    "/api/v1/services": SERVICES,
    "/api/v1/namespaces": NAMESPACES,
    "/api/v1/namespaces/kube-system/services": KUBE_DNS,
    "/api/v1/serviceaccounts": SERVICEACCOUNTS,
    "/api/v1/secrets": SECRETS,
    "/api/v1/persistentvolumeclaims": PVCS,
    "/api/v1/persistentvolumes": PVS,
    "/apis/discovery.k8s.io/v1/endpointslices": ENDPOINTSLICES,
    "/apis/networking.k8s.io/v1/networkpolicies": NETWORKPOLICIES,
    "/apis/networking.k8s.io/v1/ingresses": INGRESSES,
    "/apis/apps/v1/deployments": DEPLOYMENTS,
    "/apis/apps/v1/statefulsets": STATEFULSETS,
    "/apis/apps/v1/daemonsets": DAEMONSETS,
    "/apis/batch/v1/jobs": JOBS,
    "/apis/autoscaling/v2/horizontalpodautoscalers": HPAS,
    "/apis/storage.k8s.io/v1/storageclasses": STORAGECLASSES,
    "/apis/storage.k8s.io/v1/csidrivers": CSIDRIVERS,
    "/apis/rbac.authorization.k8s.io/v1/clusterroles": CLUSTERROLES,
    "/apis/metrics.k8s.io/v1/nodes": METRICS_NODES,
    # 未在 ROUTES 里的一律 404（模拟集群没装该 CRD，如 Gateway API）
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):     # 静音，避免刷屏
        pass

    def _send(self, code: int, payload):
        body = payload if isinstance(payload, str) else json.dumps(payload)
        raw = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ROUTES:
            self._send(200, ROUTES[path])
        elif path.startswith("/apis/gateway.networking.k8s.io/"):
            # 明确模拟"未安装 Gateway API"
            self._send(404, json.dumps({
                "kind": "Status", "apiVersion": "v1", "status": "Failure",
                "reason": "NotFound", "code": 404,
                "message": "the server could not find the requested resource",
            }))
        else:
            self._send(404, json.dumps({
                "kind": "Status", "apiVersion": "v1", "status": "Failure",
                "reason": "NotFound", "code": 404, "message": "not found: " + path,
            }))

    def do_POST(self):
        self._send(405, {"kind": "Status", "status": "Failure", "reason": "MethodNotAllowed", "code": 405})

    do_PUT = do_PATCH = do_DELETE = do_POST


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18081)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[mock-k8s] 模拟 kube-apiserver 已启动: http://{args.host}:{args.port}")
    print(f"[mock-k8s] 共 {len(ROUTES)} 个端点；Gateway API 返回 404（模拟未安装）")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[mock-k8s] 已停止")


if __name__ == "__main__":
    main()
