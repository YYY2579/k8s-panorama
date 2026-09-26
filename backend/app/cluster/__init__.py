"""K8s 集群接入模块（独立子包）。

设计约束（见 docs/design/k8s-cluster-module.md）：
- 只读：客户端白名单，代码里不存在 post/put/patch/delete 方法
- 隔离：本包禁止 import app.crud / app.routers.atlas，避免与知识图谱数据耦合
- 降级：集群不可达返回 503 + degraded，不影响其它接口
"""
