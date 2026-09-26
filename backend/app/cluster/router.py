"""集群接入路由：只读，全部挂在 /api/cluster 下。

本文件**不 import** app.crud / app.routers.atlas —— 与知识图谱数据物理隔离。
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import User
from .cache import SnapshotStore, TTLCache
from .client import ReadOnlyKubeClient, client_from_env
from .errors import ClusterAuthError, ClusterNotConfigured, ClusterUnreachable
from .snapshot import build_components, collect

router = APIRouter(prefix="/cluster", tags=["集群接入"])

_cache = TTLCache(ttl=float(os.getenv("ATLAS_K8S_CACHE_TTL", "10")))
_last_good = SnapshotStore()


def _get_client() -> ReadOnlyKubeClient:
    client = client_from_env()
    if client is None:
        raise ClusterNotConfigured()
    return client


def _handle(exc: ClusterUnreachable | ClusterAuthError | ClusterNotConfigured):
    """统一转 503 + degraded；集群不可用不该是 500。"""
    raise HTTPException(status_code=503, detail={
        "degraded": True,
        "reason": exc.reason,
        "message": exc.message,
        "hint": "集群视图已降级；其余功能不受影响",
    })


@router.get("/status", summary="集群可达性与汇总")
def status(_: User = Depends(current_user)):
    """需要登录（避免把集群信息暴露给未认证访问者）。"""
    try:
        client = _get_client()
        snap = _cache.get_or_fetch("snapshot", lambda: collect(client))
    except (ClusterUnreachable, ClusterAuthError, ClusterNotConfigured) as e:
        # 有上一次成功快照就返回它，并标注数据可能过期
        if _last_good.value:
            return {
                "degraded": True,
                "reason": e.reason,
                "message": e.message,
                "stale": True,
                "taken_at": _last_good.taken_at,
                "components": _last_good.value,
            }
        _handle(e)

    _last_good.value = build_components(snap)
    _last_good.taken_at = snap["elapsed_ms"]
    return {
        "degraded": False,
        "api_server": client.api_server,
        "elapsed_ms": snap["elapsed_ms"],
        "version": _extract_version(snap),
        "components": _last_good.value,
        "cache": _cache.stats(),
    }


@router.get("/components", summary="组件 ID → 集群实存状态")
def components(_: User = Depends(current_user)):
    """与 /status 同源，单独提供便于前端按需拉取。"""
    try:
        client = _get_client()
        snap = _cache.get_or_fetch("snapshot", lambda: collect(client))
    except (ClusterUnreachable, ClusterAuthError, ClusterNotConfigured) as e:
        _handle(e)
    return {"items": build_components(snap), "elapsed_ms": snap["elapsed_ms"]}


@router.get("/nodes", summary="Node 列表")
def nodes(_: User = Depends(current_user)):
    try:
        client = _get_client()
        data = _cache.get_or_fetch("/api/v1/nodes", lambda: client.get("/api/v1/nodes"))
    except (ClusterUnreachable, ClusterAuthError, ClusterNotConfigured) as e:
        _handle(e)
    from . import mapper
    return mapper.summarize_nodes(data.get("items", []))


@router.get("/workloads", summary="工作负载汇总")
def workloads(namespace: str | None = Query(None), _: User = Depends(current_user)):
    try:
        client = _get_client()
        ns = f"/namespaces/{namespace}" if namespace else ""
        paths = {
            "Deployment": f"/apis/apps/v1{ns}/deployments",
            "StatefulSet": f"/apis/apps/v1{ns}/statefulsets",
            "DaemonSet": f"/apis/apps/v1{ns}/daemonsets",
        }
        out = {}
        for kind, path in paths.items():
            try:
                data = client.get(path)
                out[kind] = _summarize(kind, data)
            except Exception:
                out[kind] = {"kind": kind, "total": 0, "desired": 0, "ready": 0, "degraded": []}
        return out
    except (ClusterUnreachable, ClusterAuthError, ClusterNotConfigured) as e:
        _handle(e)


def _summarize(kind: str, data: dict) -> dict:
    from . import mapper
    return mapper.summarize_workloads(data.get("items", []), kind)


def _extract_version(snap: dict) -> str:
    from . import mapper
    entry = snap["raw"].get("/version")
    if entry and entry.get("data"):
        return mapper.version_of(entry["data"])
    return "unknown"
