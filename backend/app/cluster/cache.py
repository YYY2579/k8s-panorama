"""TTL 内存缓存 + 同 key 并发去重。

- 不落盘、不做历史（需要历史对比时再考虑 cluster_snapshot 表）
- 同一 key 在飞行期内只打一次 API，避免前端连续切换把 apiserver 打爆
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class CacheEntry:
    value: Any
    expires_at: float


class TTLCache:
    def __init__(self, ttl: float = 10.0):
        self.ttl = ttl
        self._data: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        self._inflight: dict[str, threading.Event] = {}

    def get_or_fetch(self, key: str, fetcher: Callable[[], Any], ttl: float | None = None) -> Any:
        """取缓存；没有则调 fetcher（同 key 并发只调一次）。"""
        effective_ttl = self.ttl if ttl is None else ttl

        with self._lock:
            hit = self._data.get(key)
            if hit and hit.expires_at > time.monotonic():
                return hit.value

            ev = self._inflight.get(key)
            if ev is not None:
                # 已有请求在飞行：等它完成后直接拿结果
                wait_ev = ev
            else:
                wait_ev = None
                self._inflight[key] = threading.Event()

        if wait_ev is not None:
            wait_ev.wait(timeout=30)
            with self._lock:
                hit = self._data.get(key)
            if hit and hit.expires_at > time.monotonic():
                return hit.value
            # 等到的结果已过期或失败：退回自己再取一次
            return self.get_or_fetch(key, fetcher, ttl)

        try:
            value = fetcher()
        except Exception:
            with self._lock:
                ev = self._inflight.pop(key, None)
            if ev:
                ev.set()
            raise
        else:
            with self._lock:
                self._data[key] = CacheEntry(value, time.monotonic() + effective_ttl)
                self._inflight.pop(key, None)
                ev = self._inflight.get(key)
            if ev:
                ev.set()
            return value

    def invalidate(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._data.clear()
            else:
                self._data.pop(key, None)

    def stats(self) -> dict:
        with self._lock:
            now = time.monotonic()
            return {
                "entries": len(self._data),
                "fresh": sum(1 for e in self._data.values() if e.expires_at > now),
                "ttl": self.ttl,
            }


@dataclass
class SnapshotStore:
    """最近一次成功快照，供降级时使用。"""

    value: dict | None = None
    taken_at: float = 0.0
    source: str = field(default="")
