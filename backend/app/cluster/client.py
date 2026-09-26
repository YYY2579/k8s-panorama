"""kube-apiserver 只读客户端。

白名单实现：对外只有 `get()` 一个方法，代码里不存在写方法 ——
不是"不调用"，是"没有"，从根上排除误写集群的可能。

支持两种凭证来源：
1. ATLAS_K8S_API + ATLAS_K8S_TOKEN（直接指定，测试/内网方便）
2. kubeconfig 文件（ATLAS_KUBECONFIG 或 ~/.kube/config）—— 只读取，不写回
"""
from __future__ import annotations

import base64
import json
import os
import ssl
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from .errors import ClusterAuthError, ClusterUnreachable

ALLOWED_METHODS = ("GET",)
DEFAULT_TIMEOUT = float(os.getenv("ATLAS_K8S_TIMEOUT", "5"))


class ReadOnlyKubeClient:
    """只读 kube-apiserver 客户端。"""

    def __init__(
        self,
        api_server: str,
        token: str = "",
        timeout: float = DEFAULT_TIMEOUT,
        verify_tls: bool = True,
        ca_cert: str | None = None,
    ):
        self.api_server = api_server.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.verify_tls = verify_tls
        self.ca_cert = ca_cert
        self._ctx = self._build_ssl_context()

    # ---------------- 公开方法（只有 GET） ----------------
    def get(self, path: str) -> dict:
        """发起一次 GET 请求，返回解析后的 JSON。

        任何失败都转成 ClusterUnreachable / ClusterAuthError，
        由路由层统一转成 503，不把底层异常漏给调用方。
        """
        url = self.api_server + path
        req = urllib.request.Request(url, method="GET")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", "k8s-panorama/1.1")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self._ctx) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise ClusterAuthError(f"认证/授权失败（HTTP {e.code}）：请检查 token 与 RBAC") from e
            if e.code == 404:
                # 404 表示该资源类型不存在（如集群没装 Gateway API），由 mapper 判 not_detected
                raise ResourceNotFound(path) from e
            raise ClusterUnreachable(f"API 返回 HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as e:
            raise ClusterUnreachable(f"无法连接 {self.api_server}：{e}") from e
        except json.JSONDecodeError as e:
            raise ClusterUnreachable(f"响应不是合法 JSON：{e}") from e

    # ---------------- 内部 ----------------
    def _build_ssl_context(self):
        if not self.api_server.startswith("https"):
            return None
        if not self.verify_tls:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        if self.ca_cert:
            return ssl.create_default_context(cafile=self.ca_cert)
        return ssl.create_default_context()


class ResourceNotFound(Exception):
    """某个 API 路径 404：通常意味着集群没装对应 CRD/资源。"""


def client_from_env() -> ReadOnlyKubeClient | None:
    """按环境变量构造客户端；未配置返回 None（集群视图进入降级态）。"""
    api = os.getenv("ATLAS_K8S_API")
    token = os.getenv("ATLAS_K8S_TOKEN", "")

    if not api:
        cfg = _load_kubeconfig(os.getenv("ATLAS_KUBECONFIG") or str(Path.home() / ".kube" / "config"))
        if cfg:
            api, token = cfg

    if not api:
        return None

    verify = os.getenv("ATLAS_K8S_VERIFY_TLS", "1") == "1"
    ca = os.getenv("ATLAS_K8S_CA_CERT") or None
    return ReadOnlyKubeClient(api_server=api, token=token, verify_tls=verify, ca_cert=ca)


def _load_kubeconfig(path: str) -> tuple[str, str] | None:
    """从 kubeconfig 取 current-context 的 server 与 token。

    只读取，不修改文件。解析失败返回 None，由调用方按"未配置"处理。
    """
    p = Path(path)
    if not p.exists():
        return None
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return None

    # 不引入 PyYAML：手工解析需要的三个字段，足够覆盖常见内网集群
    def _field(block: str, key: str) -> str | None:
        m = re_search(rf"^\s*{key}:\s*(.+)$", block, re.M)
        return m.group(1).strip().strip('"').strip("'") if m else None

    try:
        import re as _re

        def re_search(pattern, text, flags=0):
            return _re.search(pattern, text, flags)

        current = _field(text, "current-context")
        # 找第一个 cluster/server 与第一个 user/token（简化：取首个 context）
        server = _field(text, "server")
        token = _field(text, "token")
        if server and server.startswith("http"):
            return server, token or ""
    except Exception:
        return None
    return None


def token_from_serviceaccount(mount: str = "/var/run/secrets/kubernetes.io/serviceaccount") -> tuple[str, str] | None:
    """Pod 内运行时：从 ServiceAccount 挂载点读 token 与 API 地址。"""
    base = Path(mount)
    try:
        token = (base / "token").read_text(encoding="utf-8").strip()
        host = os.getenv("KUBERNETES_SERVICE_HOST", "")
        port = os.getenv("KUBERNETES_SERVICE_PORT", "443")
        if token and host:
            return f"https://{host}:{port}", token
    except OSError:
        pass
    return None


def decode_b64(s: str) -> str:
    """kubeconfig 里 certificate-authority-data 等字段是 base64。"""
    try:
        return base64.b64decode(s).decode("utf-8")
    except Exception:
        return ""


def write_temp_ca(pem: str) -> str | None:
    """把 CA  PEM 写到临时文件供 ssl 使用；失败返回 None。"""
    if not pem.strip():
        return None
    try:
        fd, path = tempfile.mkstemp(suffix=".crt", prefix="k8s-ca-")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(pem)
        return path
    except OSError:
        return None
