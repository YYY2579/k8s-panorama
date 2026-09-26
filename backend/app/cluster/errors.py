"""集群模块的异常类型。

统一在路由层转成 503 + degraded，绝不把底层堆栈漏给前端。
"""


class ClusterError(Exception):
    """集群模块错误的基类。"""

    def __init__(self, message: str, *, reason: str = "cluster_error"):
        super().__init__(message)
        self.message = message
        self.reason = reason


class ClusterUnreachable(ClusterError):
    """连不上 apiserver、超时、或返回了非预期状态码。"""

    def __init__(self, message: str):
        super().__init__(message, reason="unreachable")


class ClusterAuthError(ClusterError):
    """token 无效或 RBAC 不足。"""

    def __init__(self, message: str):
        super().__init__(message, reason="auth")


class ClusterNotConfigured(ClusterError):
    """没有配置任何集群凭证。"""

    def __init__(self, message: str = "尚未配置集群：请设置 ATLAS_K8S_API + ATLAS_K8S_TOKEN，或提供 kubeconfig"):
        super().__init__(message, reason="not_configured")
