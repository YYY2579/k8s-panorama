"""种子数据：首次启动时建表并灌入。

数据来源：与参考图逐字核对过的图谱数据（41 个组件 / 42 条关系 / 8 个分组 / 8 个分类），
由 scripts/_gen_seed.py 从复刻版 HTML 中自动提取，未经手工转录。

知识条目 / 排障 SOP / YAML 片段为可编辑的示例内容，在界面上就能改。
"""

LAYERS = [
  {
    "id": "control",
    "label": "控制面",
    "color": "#4FA3F7"
  },
  {
    "id": "dataplane",
    "label": "数据面",
    "color": "#4ADE80"
  },
  {
    "id": "l7",
    "label": "L7/入口",
    "color": "#A855F7"
  },
  {
    "id": "portnat",
    "label": "端口/NAT",
    "color": "#FB923C"
  },
  {
    "id": "policy",
    "label": "策略",
    "color": "#F87171"
  },
  {
    "id": "observe",
    "label": "观测",
    "color": "#2DD4BF"
  },
  {
    "id": "monitor",
    "label": "监控",
    "color": "#38BDF8"
  },
  {
    "id": "storage",
    "label": "存储",
    "color": "#FBBF24"
  }
]

GROUPS = [
  {
    "id": "g1",
    "ordinal": "①",
    "title": "控制面 Control Plane",
    "subtitle": "（官方组件）",
    "x": 20,
    "y": 20,
    "w": 1460,
    "h": 256
  },
  {
    "id": "g2",
    "ordinal": "②",
    "title": "节点组件",
    "subtitle": "kubelet / CRI / kube-proxy / CNI",
    "x": 20,
    "y": 296,
    "w": 1046,
    "h": 172
  },
  {
    "id": "g3",
    "ordinal": "③",
    "title": "集群网络模型",
    "subtitle": "Service / EndpointSlice",
    "x": 20,
    "y": 488,
    "w": 1246,
    "h": 172
  },
  {
    "id": "g4",
    "ordinal": "④",
    "title": "北向入口",
    "subtitle": "Ingress 与 Gateway API",
    "x": 20,
    "y": 680,
    "w": 846,
    "h": 172
  },
  {
    "id": "g5",
    "ordinal": "⑤",
    "title": "工作负载",
    "subtitle": "",
    "x": 20,
    "y": 872,
    "w": 1246,
    "h": 172
  },
  {
    "id": "g6",
    "ordinal": "⑦",
    "title": "存储 CSI",
    "subtitle": "",
    "x": 20,
    "y": 1064,
    "w": 960,
    "h": 172
  },
  {
    "id": "g7",
    "ordinal": "⑧",
    "title": "安全",
    "subtitle": "RBAC / PSA / Admission",
    "x": 20,
    "y": 1256,
    "w": 1086,
    "h": 172
  },
  {
    "id": "g8",
    "ordinal": "⑨",
    "title": "可观测",
    "subtitle": "",
    "x": 20,
    "y": 1448,
    "w": 846,
    "h": 172
  }
]

NODES = [
  {
    "id": "apiserver",
    "group_id": "g1",
    "layer_id": "control",
    "name": "kube-apiserver",
    "kind": "控制面组件",
    "summary": "所有组件与客户端的唯一入口，负责认证、鉴权、准入与持久化到 etcd。",
    "cmd": "kubectl cluster-info",
    "x": 40,
    "y": 74,
    "fields": [
      {
        "label": "端口",
        "value": "HTTPS :6443"
      }
    ]
  },
  {
    "id": "etcd",
    "group_id": "g1",
    "layer_id": "control",
    "name": "etcd",
    "kind": "控制面组件",
    "summary": "集群唯一可信数据源，保存全部 API 对象的最终状态。",
    "cmd": "kubectl -n kube-system exec etcd-master -- etcdctl endpoint health",
    "x": 260,
    "y": 74,
    "fields": [
      {
        "label": "client",
        "value": "2379"
      }
    ]
  },
  {
    "id": "scheduler",
    "group_id": "g1",
    "layer_id": "control",
    "name": "kube-scheduler",
    "kind": "控制面组件",
    "summary": "监听 Pending Pod，按资源、亲和与污点约束选择目标节点。",
    "cmd": "kubectl -n kube-system logs deploy/kube-scheduler",
    "x": 480,
    "y": 74,
    "fields": [
      {
        "label": "输入",
        "value": "Pending Pod"
      }
    ]
  },
  {
    "id": "kcm",
    "group_id": "g1",
    "layer_id": "control",
    "name": "kube-controller-manager",
    "kind": "控制面组件",
    "summary": "内置控制器集合，持续把实际状态拉回期望状态。",
    "cmd": "kubectl -n kube-system logs deploy/kube-controller-manager",
    "x": 700,
    "y": 74,
    "fields": [
      {
        "label": "输出",
        "value": "Node / RS / orphaned"
      }
    ]
  },
  {
    "id": "ccm",
    "group_id": "g1",
    "layer_id": "control",
    "name": "cloud-controller-manager",
    "kind": "可选云组件",
    "summary": "把集群与云厂商解耦，接管 Node、Route、Service 三类云相关控制器。",
    "cmd": "kubectl -n kube-system logs deploy/cloud-controller-manager",
    "x": 820,
    "y": 180,
    "fields": [
      {
        "label": "控制器",
        "value": "Node / Route / Service"
      }
    ]
  },
  {
    "id": "admission",
    "group_id": "g1",
    "layer_id": "policy",
    "name": "Admission",
    "kind": "准入阶段",
    "summary": "请求落库前的最后一道闸门，可改写也可拒绝。",
    "cmd": "kubectl get validatingwebhookconfiguration",
    "x": 1060,
    "y": 180,
    "fields": [
      {
        "label": "阶段",
        "value": "Mutating / Validating / CEL"
      }
    ]
  },
  {
    "id": "coredns",
    "group_id": "g1",
    "layer_id": "control",
    "name": "CoreDNS",
    "kind": "集群 DNS 组件",
    "summary": "为 Service 与 Pod 提供集群内域名解析。",
    "cmd": "kubectl -n kube-system get svc kube-dns",
    "x": 1300,
    "y": 180,
    "fields": [
      {
        "label": "名称",
        "value": "kube-dns.kube-system"
      }
    ]
  },
  {
    "id": "kubelet",
    "group_id": "g2",
    "layer_id": "control",
    "name": "kubelet",
    "kind": "节点组件",
    "summary": "节点代理，负责 Pod 生命周期与容器运行时交互。",
    "cmd": "systemctl status kubelet",
    "x": 40,
    "y": 346,
    "fields": [
      {
        "label": "端口",
        "value": "HTTPS :10250"
      }
    ]
  },
  {
    "id": "runtime",
    "group_id": "g2",
    "layer_id": "dataplane",
    "name": "容器运行时",
    "kind": "containerd / CRI-O",
    "summary": "真正拉起容器的组件，通过 CRI 对上、OCI 对下。",
    "cmd": "crictl ps -a",
    "x": 240,
    "y": 346,
    "fields": [
      {
        "label": "类型",
        "value": "OCI gRPC"
      }
    ]
  },
  {
    "id": "kube-proxy",
    "group_id": "g2",
    "layer_id": "dataplane",
    "name": "kube-proxy",
    "kind": "节点组件",
    "summary": "把 Service 抽象翻译成节点上的转发规则。",
    "cmd": "kubectl -n kube-system logs ds/kube-proxy",
    "x": 440,
    "y": 346,
    "fields": [
      {
        "label": "输出",
        "value": "iptables / IPVS 转发规则"
      }
    ]
  },
  {
    "id": "cni",
    "group_id": "g2",
    "layer_id": "dataplane",
    "name": "CNI 插件",
    "kind": "Flannel / Calico / Cilium",
    "summary": "为 Pod 分配 IP 并打通跨节点网络。",
    "cmd": "ls /etc/cni/net.d",
    "x": 640,
    "y": 346,
    "fields": [
      {
        "label": "实现",
        "value": "veth / 路由 / eBPF"
      }
    ]
  },
  {
    "id": "node",
    "group_id": "g2",
    "layer_id": "control",
    "name": "Node",
    "kind": "节点资源载体",
    "summary": "承载 Pod 的物理或虚拟机，向上汇报可分配资源。",
    "cmd": "kubectl get nodes -o wide",
    "x": 840,
    "y": 346,
    "fields": [
      {
        "label": "可分配",
        "value": "cpu / memory / pods"
      }
    ]
  },
  {
    "id": "service",
    "group_id": "g3",
    "layer_id": "dataplane",
    "name": "Service",
    "kind": "集群组件",
    "summary": "为一组 Pod 提供稳定的虚拟 IP 与负载均衡。",
    "cmd": "kubectl get svc -A",
    "x": 40,
    "y": 538,
    "fields": [
      {
        "label": "类型",
        "value": "ClusterIP / L4 LB"
      }
    ]
  },
  {
    "id": "endpointslice",
    "group_id": "g3",
    "layer_id": "dataplane",
    "name": "EndpointSlice",
    "kind": "集群组件",
    "summary": "Service 背后的真实后端地址清单。",
    "cmd": "kubectl get endpointslice -A",
    "x": 240,
    "y": 538,
    "fields": [
      {
        "label": "类型",
        "value": "Service → 地址 + Port"
      }
    ]
  },
  {
    "id": "netpol",
    "group_id": "g3",
    "layer_id": "policy",
    "name": "NetworkPolicy",
    "kind": "策略组件",
    "summary": "被选中后默认拒绝未声明流量。需 CNI 实现。",
    "cmd": "kubectl get networkpolicy -A",
    "x": 440,
    "y": 538,
    "fields": [
      {
        "label": "结果",
        "value": "ALLOW / DENY"
      }
    ]
  },
  {
    "id": "overlay",
    "group_id": "g3",
    "layer_id": "portnat",
    "name": "Overlay / Underlay",
    "kind": "网络封装模式",
    "summary": "决定跨节点报文的封装方式与转发路径。",
    "cmd": "ip -d link show flannel.1",
    "x": 640,
    "y": 538,
    "fields": [
      {
        "label": "类型",
        "value": "VXLAN / BGP / VLAN"
      }
    ]
  },
  {
    "id": "ebpf",
    "group_id": "g3",
    "layer_id": "dataplane",
    "name": "eBPF datapath",
    "kind": "CNI 数据面",
    "summary": "绕过 iptables 的内核级转发与负载均衡。",
    "cmd": "cilium bpf lb list",
    "x": 840,
    "y": 538,
    "fields": [
      {
        "label": "命令",
        "value": "cilium bpf lb list"
      }
    ]
  },
  {
    "id": "envoy",
    "group_id": "g3",
    "layer_id": "l7",
    "name": "Envoy",
    "kind": "L7 代理组件",
    "summary": "七层代理与可观测数据面，常与服务网格搭配。",
    "cmd": "kubectl exec -it deploy/app -- curl -s localhost:9901/stats",
    "x": 1040,
    "y": 538,
    "fields": [
      {
        "label": "模式",
        "value": "SIDECAR / INGRESS"
      }
    ]
  },
  {
    "id": "ingress",
    "group_id": "g4",
    "layer_id": "l7",
    "name": "Ingress",
    "kind": "L7 入口组件",
    "summary": "七层路由的最简声明式入口。",
    "cmd": "kubectl get ingress -A",
    "x": 40,
    "y": 730,
    "fields": [
      {
        "label": "类型",
        "value": "host / path"
      }
    ]
  },
  {
    "id": "gatewayclass",
    "group_id": "g4",
    "layer_id": "l7",
    "name": "GatewayClass",
    "kind": "网络组件",
    "summary": "指定由哪个控制器来实现 Gateway。",
    "cmd": "kubectl get gatewayclass",
    "x": 240,
    "y": 730,
    "fields": [
      {
        "label": "类型",
        "value": "Gateway controller"
      }
    ]
  },
  {
    "id": "gateway",
    "group_id": "g4",
    "layer_id": "l7",
    "name": "Gateway",
    "kind": "L7 入口组件",
    "summary": "Gateway API 中的监听器与证书挂载点。",
    "cmd": "kubectl get gateway -A",
    "x": 440,
    "y": 730,
    "fields": [
      {
        "label": "名称",
        "value": "controllerName → Secret"
      }
    ]
  },
  {
    "id": "httproute",
    "group_id": "g4",
    "layer_id": "l7",
    "name": "HTTPRoute",
    "kind": "L7 路由组件",
    "summary": "比 Ingress 表达力更强的七层路由规则。",
    "cmd": "kubectl get httproute -A",
    "x": 640,
    "y": 730,
    "fields": [
      {
        "label": "匹配",
        "value": "host / path / header / method"
      }
    ]
  },
  {
    "id": "pod",
    "group_id": "g5",
    "layer_id": "dataplane",
    "name": "Pod",
    "kind": "最小调度单元",
    "summary": "K8s 的最小可调度单位，一个或多个共享网络的容器。",
    "cmd": "kubectl get pods -o wide",
    "x": 40,
    "y": 922,
    "fields": [
      {
        "label": "承载",
        "value": "liveness / readiness / startup"
      }
    ]
  },
  {
    "id": "deployment",
    "group_id": "g5",
    "layer_id": "dataplane",
    "name": "Deployment",
    "kind": "无状态组件",
    "summary": "通过 ReplicaSet 实现无状态应用的滚动更新与回滚。",
    "cmd": "kubectl get deploy -A",
    "x": 240,
    "y": 922,
    "fields": [
      {
        "label": "策略",
        "value": "ReplicaSet"
      }
    ]
  },
  {
    "id": "statefulset",
    "group_id": "g5",
    "layer_id": "dataplane",
    "name": "StatefulSet",
    "kind": "有状态组件",
    "summary": "为每个副本提供稳定标识与独立存储。",
    "cmd": "kubectl get sts -A",
    "x": 440,
    "y": 922,
    "fields": [
      {
        "label": "字段",
        "value": "volumeClaimTemplate"
      }
    ]
  },
  {
    "id": "daemonset",
    "group_id": "g5",
    "layer_id": "dataplane",
    "name": "DaemonSet",
    "kind": "每节点组件",
    "summary": "保证每个（或指定的）节点上都跑一个副本。",
    "cmd": "kubectl get ds -A",
    "x": 640,
    "y": 922,
    "fields": [
      {
        "label": "选择器",
        "value": "nodeSelector / affinity"
      }
    ]
  },
  {
    "id": "job",
    "group_id": "g5",
    "layer_id": "dataplane",
    "name": "Job / CronJob",
    "kind": "任务组件",
    "summary": "运行一次或按计划运行的批处理任务。",
    "cmd": "kubectl get jobs -A",
    "x": 840,
    "y": 922,
    "fields": [
      {
        "label": "字段",
        "value": "completions / parallelism"
      }
    ]
  },
  {
    "id": "hpa",
    "group_id": "g5",
    "layer_id": "control",
    "name": "HPA",
    "kind": "弹性组件",
    "summary": "按指标自动调整工作负载副本数。",
    "cmd": "kubectl get hpa -A",
    "x": 1040,
    "y": 922,
    "fields": [
      {
        "label": "API",
        "value": "autoscaling/v1"
      }
    ]
  },
  {
    "id": "pvc",
    "group_id": "g6",
    "layer_id": "storage",
    "name": "PVC",
    "kind": "存储组件",
    "summary": "用户侧的存储需求声明，与 PV 一一绑定。",
    "cmd": "kubectl get pvc -A",
    "x": 40,
    "y": 1114,
    "fields": [
      {
        "label": "绑定",
        "value": "PV"
      }
    ]
  },
  {
    "id": "pv",
    "group_id": "g6",
    "layer_id": "storage",
    "name": "PersistentVolume",
    "kind": "存储组件",
    "summary": "集群侧的存储资源实体，独立于 Pod 生命周期。",
    "cmd": "kubectl get pv",
    "x": 240,
    "y": 1114,
    "fields": [
      {
        "label": "字段",
        "value": "hostPath / NFS"
      }
    ]
  },
  {
    "id": "storageclass",
    "group_id": "g6",
    "layer_id": "storage",
    "name": "StorageClass",
    "kind": "存储组件",
    "summary": "描述存储的提供者与参数，支持动态供给。",
    "cmd": "kubectl get storageclass",
    "x": 460,
    "y": 1114,
    "fields": [
      {
        "label": "默认",
        "value": "storageclass.kubernetes.io/is-default-class"
      }
    ]
  },
  {
    "id": "csidriver",
    "group_id": "g6",
    "layer_id": "storage",
    "name": "CSI Driver",
    "kind": "存储组件",
    "summary": "以标准接口对接外部存储系统。",
    "cmd": "kubectl get csidrivers",
    "x": 780,
    "y": 1114,
    "fields": [
      {
        "label": "能力",
        "value": "snapshot / csi / resize"
      }
    ]
  },
  {
    "id": "rbac",
    "group_id": "g7",
    "layer_id": "policy",
    "name": "RBAC",
    "kind": "权限组件",
    "summary": "基于角色的访问控制，决定谁能对什么资源做什么。",
    "cmd": "kubectl get clusterrole,clusterrolebinding",
    "x": 40,
    "y": 1306,
    "fields": [
      {
        "label": "包含字段",
        "value": "user / group / role / rolebinding / serviceaccounts"
      }
    ]
  },
  {
    "id": "sa",
    "group_id": "g7",
    "layer_id": "policy",
    "name": "ServiceAccount",
    "kind": "工作负载身份",
    "summary": "Pod 访问 API Server 时使用的身份凭证。",
    "cmd": "kubectl get sa -A",
    "x": 240,
    "y": 1306,
    "fields": [
      {
        "label": "字段",
        "value": "Token"
      }
    ]
  },
  {
    "id": "secret",
    "group_id": "g7",
    "layer_id": "policy",
    "name": "Secret",
    "kind": "敏感信息",
    "summary": "承载口令、证书与令牌，需配合加密存储使用。",
    "cmd": "kubectl get secret -A",
    "x": 440,
    "y": 1306,
    "fields": [
      {
        "label": "字段",
        "value": "value / env"
      }
    ]
  },
  {
    "id": "psa",
    "group_id": "g7",
    "layer_id": "policy",
    "name": "Pod Security Admission",
    "kind": "安全组件",
    "summary": "按命名空间统一约束 Pod 的安全上下文。",
    "cmd": "kubectl get ns -L pod-security.kubernetes.io/enforce",
    "x": 640,
    "y": 1306,
    "fields": [
      {
        "label": "字段",
        "value": "pod-security.kubernetes.io/*"
      }
    ]
  },
  {
    "id": "vap",
    "group_id": "g7",
    "layer_id": "policy",
    "name": "ValidatingAdmissionPolicy",
    "kind": "CEL 策略",
    "summary": "用 CEL 表达式做原生参数化校验，替代部分 webhook。",
    "cmd": "kubectl get validatingadmissionpolicy",
    "x": 840,
    "y": 1306,
    "fields": [
      {
        "label": "语法",
        "value": "CEL"
      }
    ]
  },
  {
    "id": "metricsserver",
    "group_id": "g8",
    "layer_id": "monitor",
    "name": "metrics-server",
    "kind": "资源指标",
    "summary": "提供 CPU/内存等资源指标，供 HPA 与 kubectl top 使用。",
    "cmd": "kubectl top nodes",
    "x": 40,
    "y": 1498,
    "fields": [
      {
        "label": "API",
        "value": "metrics.k8s.io"
      }
    ]
  },
  {
    "id": "prometheus",
    "group_id": "g8",
    "layer_id": "observe",
    "name": "Prometheus",
    "kind": "指标采集",
    "summary": "指标库与告警引擎，K8s 可观测事实标准。",
    "cmd": "curl -s localhost:9090/api/v1/targets",
    "x": 240,
    "y": 1498,
    "fields": [
      {
        "label": "接口",
        "value": "/metrics /api/v1/query"
      }
    ]
  },
  {
    "id": "logs",
    "group_id": "g8",
    "layer_id": "observe",
    "name": "集群日志",
    "kind": "节点 agent → 收集",
    "summary": "统一收集各节点容器日志并汇聚检索。",
    "cmd": "kubectl -n logging logs ds/fluent-bit",
    "x": 440,
    "y": 1498,
    "fields": [
      {
        "label": "类型",
        "value": "fluentbit / agent"
      }
    ]
  },
  {
    "id": "hubble",
    "group_id": "g8",
    "layer_id": "observe",
    "name": "Hubble",
    "kind": "eBPF 流日志",
    "summary": "基于 eBPF 的网络流可观测性，看清每一次连接。",
    "cmd": "hubble observe --follow",
    "x": 640,
    "y": 1498,
    "fields": [
      {
        "label": "指标",
        "value": "HUBBLE / DROPDNS"
      }
    ]
  }
]

EDGES = [
  {
    "id": "apiserver->etcd",
    "from_node": "apiserver",
    "to_node": "etcd",
    "label": "get/watch",
    "layer_id": "control",
    "sort_order": 0
  },
  {
    "id": "scheduler->apiserver",
    "from_node": "scheduler",
    "to_node": "apiserver",
    "label": "watch Pod",
    "layer_id": "control",
    "sort_order": 1
  },
  {
    "id": "kcm->apiserver",
    "from_node": "kcm",
    "to_node": "apiserver",
    "label": "apply",
    "layer_id": "control",
    "sort_order": 2
  },
  {
    "id": "ccm->apiserver",
    "from_node": "ccm",
    "to_node": "apiserver",
    "label": "client",
    "layer_id": "control",
    "sort_order": 3
  },
  {
    "id": "admission->apiserver",
    "from_node": "admission",
    "to_node": "apiserver",
    "label": "webhook",
    "layer_id": "policy",
    "sort_order": 4
  },
  {
    "id": "coredns->apiserver",
    "from_node": "coredns",
    "to_node": "apiserver",
    "label": "client",
    "layer_id": "control",
    "sort_order": 5
  },
  {
    "id": "kubelet->apiserver",
    "from_node": "kubelet",
    "to_node": "apiserver",
    "label": "HTTPS :6443",
    "layer_id": "control",
    "sort_order": 6
  },
  {
    "id": "kube-proxy->apiserver",
    "from_node": "kube-proxy",
    "to_node": "apiserver",
    "label": "watch",
    "layer_id": "dataplane",
    "sort_order": 7
  },
  {
    "id": "node->kubelet",
    "from_node": "node",
    "to_node": "kubelet",
    "label": "kubelet",
    "layer_id": "control",
    "sort_order": 8
  },
  {
    "id": "runtime->kubelet",
    "from_node": "runtime",
    "to_node": "kubelet",
    "label": "CRI gRPC",
    "layer_id": "dataplane",
    "sort_order": 9
  },
  {
    "id": "cni->runtime",
    "from_node": "cni",
    "to_node": "runtime",
    "label": "CNI",
    "layer_id": "dataplane",
    "sort_order": 10
  },
  {
    "id": "kube-proxy->service",
    "from_node": "kube-proxy",
    "to_node": "service",
    "label": "同步",
    "layer_id": "dataplane",
    "sort_order": 11
  },
  {
    "id": "service->endpointslice",
    "from_node": "service",
    "to_node": "endpointslice",
    "label": "selector",
    "layer_id": "dataplane",
    "sort_order": 12
  },
  {
    "id": "endpointslice->pod",
    "from_node": "endpointslice",
    "to_node": "pod",
    "label": "endpoint",
    "layer_id": "dataplane",
    "sort_order": 13
  },
  {
    "id": "netpol->pod",
    "from_node": "netpol",
    "to_node": "pod",
    "label": "策略",
    "layer_id": "policy",
    "sort_order": 14
  },
  {
    "id": "overlay->pod",
    "from_node": "overlay",
    "to_node": "pod",
    "label": "封装",
    "layer_id": "portnat",
    "sort_order": 15
  },
  {
    "id": "ebpf->kube-proxy",
    "from_node": "ebpf",
    "to_node": "kube-proxy",
    "label": "LB",
    "layer_id": "dataplane",
    "sort_order": 16
  },
  {
    "id": "envoy->service",
    "from_node": "envoy",
    "to_node": "service",
    "label": "L7",
    "layer_id": "l7",
    "sort_order": 17
  },
  {
    "id": "ingress->service",
    "from_node": "ingress",
    "to_node": "service",
    "label": "HTTP",
    "layer_id": "l7",
    "sort_order": 18
  },
  {
    "id": "gatewayclass->gateway",
    "from_node": "gatewayclass",
    "to_node": "gateway",
    "label": "controller",
    "layer_id": "l7",
    "sort_order": 19
  },
  {
    "id": "gateway->httproute",
    "from_node": "gateway",
    "to_node": "httproute",
    "label": "绑定",
    "layer_id": "l7",
    "sort_order": 20
  },
  {
    "id": "httproute->service",
    "from_node": "httproute",
    "to_node": "service",
    "label": "转发",
    "layer_id": "l7",
    "sort_order": 21
  },
  {
    "id": "deployment->pod",
    "from_node": "deployment",
    "to_node": "pod",
    "label": "selector",
    "layer_id": "dataplane",
    "sort_order": 22
  },
  {
    "id": "statefulset->pod",
    "from_node": "statefulset",
    "to_node": "pod",
    "label": "selector",
    "layer_id": "dataplane",
    "sort_order": 23
  },
  {
    "id": "daemonset->pod",
    "from_node": "daemonset",
    "to_node": "pod",
    "label": "selector",
    "layer_id": "dataplane",
    "sort_order": 24
  },
  {
    "id": "job->pod",
    "from_node": "job",
    "to_node": "pod",
    "label": "创建",
    "layer_id": "dataplane",
    "sort_order": 25
  },
  {
    "id": "hpa->deployment",
    "from_node": "hpa",
    "to_node": "deployment",
    "label": "扩容",
    "layer_id": "control",
    "sort_order": 26
  },
  {
    "id": "pod->pvc",
    "from_node": "pod",
    "to_node": "pvc",
    "label": "绑定",
    "layer_id": "dataplane",
    "sort_order": 27
  },
  {
    "id": "pvc->pv",
    "from_node": "pvc",
    "to_node": "pv",
    "label": "绑定",
    "layer_id": "storage",
    "sort_order": 28
  },
  {
    "id": "storageclass->pvc",
    "from_node": "storageclass",
    "to_node": "pvc",
    "label": "动态供给",
    "layer_id": "storage",
    "sort_order": 29
  },
  {
    "id": "csidriver->pv",
    "from_node": "csidriver",
    "to_node": "pv",
    "label": "挂载",
    "layer_id": "storage",
    "sort_order": 30
  },
  {
    "id": "csidriver->pod",
    "from_node": "csidriver",
    "to_node": "pod",
    "label": "挂载",
    "layer_id": "storage",
    "sort_order": 31
  },
  {
    "id": "rbac->sa",
    "from_node": "rbac",
    "to_node": "sa",
    "label": "授权",
    "layer_id": "policy",
    "sort_order": 32
  },
  {
    "id": "sa->pod",
    "from_node": "sa",
    "to_node": "pod",
    "label": "token",
    "layer_id": "policy",
    "sort_order": 33
  },
  {
    "id": "secret->pod",
    "from_node": "secret",
    "to_node": "pod",
    "label": "env / volume",
    "layer_id": "policy",
    "sort_order": 34
  },
  {
    "id": "psa->pod",
    "from_node": "psa",
    "to_node": "pod",
    "label": "准入",
    "layer_id": "policy",
    "sort_order": 35
  },
  {
    "id": "vap->apiserver",
    "from_node": "vap",
    "to_node": "apiserver",
    "label": "CEL",
    "layer_id": "policy",
    "sort_order": 36
  },
  {
    "id": "prometheus->kubelet",
    "from_node": "prometheus",
    "to_node": "kubelet",
    "label": "/metrics",
    "layer_id": "observe",
    "sort_order": 37
  },
  {
    "id": "metricsserver->kubelet",
    "from_node": "metricsserver",
    "to_node": "kubelet",
    "label": "metrics.k8s.io",
    "layer_id": "monitor",
    "sort_order": 38
  },
  {
    "id": "logs->pod",
    "from_node": "logs",
    "to_node": "pod",
    "label": "采集",
    "layer_id": "observe",
    "sort_order": 39
  },
  {
    "id": "hubble->ebpf",
    "from_node": "hubble",
    "to_node": "ebpf",
    "label": "流日志",
    "layer_id": "observe",
    "sort_order": 40
  },
  {
    "id": "ingress->pod",
    "from_node": "ingress",
    "to_node": "pod",
    "label": "注入",
    "layer_id": "l7",
    "sort_order": 41
  }
]

NOTES = [
    {
        "slug": "networkpolicy-basics",
        "node_id": "netpol",
        "title": "NetworkPolicy：默认拒绝与放行",
        "status": "published",
        "markdown": (
            "## 核心语义\n\n"
            "NetworkPolicy 按 Pod 选择器控制 L3/L4 进出。**默认未选中的 Pod 允许所有流量**；"
            "一旦被策略选中，未允许的入站（或出站，若声明 Egress）被拒绝。\n\n"
            "## 常见坑\n\n"
            "1. 策略需要 CNI 实现。Flannel 默认不生效，Calico / Cilium 才支持。\n"
            "2. podSelector 为空表示选中命名空间下全部 Pod。\n"
            "3. 只声明 ingress 不影响 egress，反之亦然。\n\n"
            "## 一句话记忆\n\n"
            "Route 决定去哪，Policy 决定是否允许。"
        ),
    },
    {
        "slug": "service-endpointslice",
        "node_id": "service",
        "title": "Service 到 Pod：中间还隔着 EndpointSlice",
        "status": "published",
        "markdown": (
            "Service 的 ClusterIP 只是**虚拟 IP**，真正转发的目标是 EndpointSlice 里记录的地址。\n\n"
            "排查 502 / 超时时的顺序：\n\n"
            "1. `kubectl get endpointslice -A` 看后端地址在不在；\n"
            "2. 地址为空 → 回去查 selector 是否匹配上 Pod 标签；\n"
            "3. 地址在但不通 → 查 kube-proxy 规则 / CNI / NetworkPolicy。"
        ),
    },
    {
        "slug": "pod-pending-triage",
        "node_id": "pod",
        "title": "Pod 一直 Pending 怎么查",
        "status": "draft",
        "markdown": (
            "按顺序排除：\n\n"
            "1. `kubectl describe pod` 看 Events；\n"
            "2. 调度失败 → 资源不足 / 污点 / 亲和性；\n"
            "3. 镜像拉取失败 → 仓库地址、密钥、网络；\n"
            "4. 存储问题 → PVC 是否 Bound。"
        ),
    },
]

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
             "command": "kubectl describe nodes | grep -A5 -E 'Taints|Allocated'"},
            {"step_no": 3, "action": "检查 PVC 是否已绑定",
             "expect": "相关 PVC 状态为 Bound",
             "command": "kubectl get pvc -A"},
        ],
    },
]

YAMLS = [
    {
        "node_id": "netpol",
        "title": "最小可用的 NetworkPolicy（默认拒绝入站）",
        "yaml": (
            "apiVersion: networking.k8s.io/v1\n"
            "kind: NetworkPolicy\n"
            "metadata:\n"
            "  name: default-deny-ingress\n"
            "  namespace: demo\n"
            "spec:\n"
            "  podSelector: {}          # 选中本命名空间全部 Pod\n"
            "  policyTypes: [\"Ingress\"]\n"
        ),
    },
    {
        "node_id": "deployment",
        "title": "最小可用的 Deployment",
        "yaml": (
            "apiVersion: apps/v1\n"
            "kind: Deployment\n"
            "metadata:\n"
            "  name: demo\n"
            "spec:\n"
            "  replicas: 2\n"
            "  selector:\n"
            "    matchLabels:\n"
            "      app: demo\n"
            "  template:\n"
            "    metadata:\n"
            "      labels:\n"
            "        app: demo\n"
            "    spec:\n"
            "      containers:\n"
            "        - name: app\n"
            "          image: nginx:1.25\n"
            "          ports:\n"
            "            - containerPort: 80\n"
        ),
    },
]


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
