#!/usr/bin/env python
"""端到端接口测试：真实请求后端，逐条打印 PASS / FAIL，最后清理自己造的数据。

用法（服务需已在 8000 端口运行）：
    python scripts/test_api.py [http://127.0.0.1:8000]
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
API = BASE + "/api"

PASS, FAIL = [], []


def req(method: str, path: str, body: dict | None = None):
    """发一次请求。

    返回 (status, data)。连接失败（服务没起）时返回 (0, {"detail": ...})，
    由调用方按失败处理，不向上抛异常。
    """
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    r = urllib.request.Request(
        API + path, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        return 0, {"detail": f"连接失败：{reason}"}


def check(name: str, ok: bool, extra: str = ""):
    (PASS if ok else FAIL).append(name)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"   {extra}" if extra else ""))


def cleanup_leftovers() -> None:
    """清掉上一轮异常中断留下的测试数据，保证可重复运行。"""
    req("DELETE", "/edges/zz-test-node->pod")
    req("DELETE", "/nodes/zz-test-node")
    req("DELETE", "/notes/zz-test-note")
    req("DELETE", "/sops/zz-test-sop")
    req("DELETE", "/groups/zz-test-group?force=true")
    _, ys = req("GET", "/yamls")
    for y in (ys if isinstance(ys, list) else []):
        if str(y.get("title", "")).startswith("测试片段"):
            req("DELETE", f"/yamls/{y['id']}")


def main() -> int:
    print(f"== K8s Panorama 端到端测试 ==  {API}\n")

    # ---------- 0 清理上轮残留（服务没起时返回 0，不抛异常） ----------
    cleanup_leftovers()

    # ---------- 1 健康检查 ----------
    st, d = req("GET", "/health")
    if st == 0:
        print(f"无法连接后端：{(d or {}).get('detail')}")
        print("请先在 backend 目录执行：python run.py")
        return 1
    check("健康检查返回 200", st == 200, str(d))
    if st != 200:
        print("后端未就绪，后续测试无法进行。")
        return 1
    base_counts = (d or {}).get("counts", {})

    # ---------- 2 图谱聚合 ----------
    st, g = req("GET", "/atlas/graph")
    check("图谱聚合返回 200", st == 200)
    check("图层 8 个", len(g["layers"]) == 8, f"实际 {len(g['layers'])}")
    check("分组 8 个", len(g["groups"]) == 8, f"实际 {len(g['groups'])}")
    check("组件 41 个", len(g["nodes"]) == 41, f"实际 {len(g['nodes'])}")
    check("关系 42 条", len(g["edges"]) == 42, f"实际 {len(g['edges'])}")
    check("组件带关键字段", bool(g["nodes"][0].get("fields") is not None))

    # ---------- 3 组件 CRUD ----------
    new_node = {
        "id": "zz-test-node", "group_id": "g3", "layer_id": "policy",
        "name": "测试组件", "kind": "测试类型", "summary": "端到端测试建的组件",
        "cmd": "kubectl get pods", "x": 1200, "y": 560,
        "fields": [{"label": "字段", "value": "值"}],
    }
    st, n1 = req("POST", "/nodes", new_node)
    check("POST 组件 返回 201", st == 201, str(st))
    check("POST 组件 内容一致", bool(n1) and n1["name"] == "测试组件")

    st, n2 = req("GET", "/nodes/zz-test-node")
    check("GET 组件详情", st == 200 and n2["id"] == "zz-test-node")
    check("组件字段落库", bool(n2.get("fields")) and n2["fields"][0]["value"] == "值")

    st, n3 = req("PATCH", "/nodes/zz-test-node", {"summary": "改过了", "fields": [{"label": "新字段", "value": "新值"}]})
    check("PATCH 组件", st == 200 and n3["summary"] == "改过了")
    check("PATCH 覆盖字段", bool(n3.get("fields")) and n3["fields"][0]["label"] == "新字段")

    # ---------- 4 关系 CRUD ----------
    st, e1 = req("POST", "/edges", {"from_node": "zz-test-node", "to_node": "pod", "label": "测试关系"})
    check("POST 关系", st == 201, str(st))
    st, _ = req("GET", "/edges/zz-test-node->pod")
    check("GET 关系详情", st == 200)
    st, e2 = req("PATCH", "/edges/zz-test-node->pod", {"label": "改后的标签"})
    check("PATCH 关系", st == 200 and e2["label"] == "改后的标签")

    # ---------- 5 搜索 ----------
    st, s1 = req("GET", "/atlas/search?q=apiserver")
    check("搜索命中组件", st == 200 and s1["total"] > 0, f"命中 {s1.get('total')}")
    st, s2 = req("GET", "/atlas/search?q=" + urllib.parse.quote("测试组件"))
    check("搜索命中新建组件", st == 200 and any(i["id"] == "zz-test-node" for i in s2["items"]))
    st, s3 = req("GET", "/atlas/search?q=" + urllib.parse.quote("网络策略"))
    check("中文搜索不报错", st == 200)

    # ---------- 6 分组 CRUD ----------
    st, gg = req("POST", "/groups", {"id": "zz-test-group", "ordinal": "⑩", "title": "测试分组", "subtitle": "", "x": 20, "y": 1800, "w": 600, "h": 170})
    check("POST 分组", st == 201, str(st))
    st, gg2 = req("PATCH", "/groups/zz-test-group", {"title": "测试分组改名"})
    check("PATCH 分组", st == 200 and gg2["title"] == "测试分组改名")
    st, gg3 = req("DELETE", "/groups/zz-test-group?force=true")
    check("DELETE 分组(force)", st == 200, str(gg3))

    # ---------- 7 知识条目 + 状态流转 ----------
    st, t1 = req("POST", "/notes", {"slug": "zz-test-note", "title": "测试条目", "markdown": "# 测试\n正文", "node_id": "pod"})
    check("POST 知识条目", st == 201, str(st))
    check("知识条目初始状态 draft", t1 and t1["status"] == "draft")

    st, t2 = req("POST", "/notes/zz-test-note/transition", {"action": "publish"})
    check("流转 publish: draft→review", st == 200 and t2["status"] == "review", str(t2.get("status")))
    st, t3 = req("POST", "/notes/zz-test-note/transition", {"action": "approve"})
    check("流转 approve: review→published", st == 200 and t3["status"] == "published", str(t3.get("status")))
    st, _ = req("POST", "/notes/zz-test-note/transition", {"action": "publish"})
    check("非法流转被拒（published 不能 publish）", st == 400, f"返回 {st}")
    st, t4 = req("POST", "/notes/zz-test-note/transition", {"action": "archive"})
    check("流转 archive", st == 200 and t4["status"] == "archived")
    st, t5 = req("POST", "/notes/zz-test-note/transition", {"action": "restore"})
    check("流转 restore: archived→draft", st == 200 and t5["status"] == "draft")
    st, _ = req("DELETE", "/notes/zz-test-note")
    check("DELETE 知识条目", st == 200)

    # ---------- 8 排障 SOP + 状态流转 ----------
    st, p1 = req("POST", "/sops", {
        "symptom": "zz-test-sop", "title": "测试 SOP", "status": "draft",
        "steps": [{"step_no": 1, "action": "看事件", "expect": "能看到原因", "command": "kubectl describe pod"}],
    })
    check("POST 排障 SOP", st == 201, str(st))
    check("SOP 步骤落库", bool(p1.get("steps")) and p1["steps"][0]["action"] == "看事件")
    st, p2 = req("POST", "/sops/zz-test-sop/transition", {"action": "publish"})
    check("SOP 流转 publish", st == 200 and p2["status"] == "review")
    st, p3 = req("POST", "/sops/zz-test-sop/transition", {"action": "approve"})
    check("SOP 流转 approve", st == 200 and p3["status"] == "published")
    st, _ = req("DELETE", "/sops/zz-test-sop")
    check("DELETE 排障 SOP", st == 200)

    # ---------- 9 YAML ----------
    st, y1 = req("POST", "/yamls", {"node_id": "pod", "title": "测试片段", "yaml": "kind: Pod\n"})
    check("POST YAML", st == 201, str(st))
    yid = (y1 or {}).get("id")
    st, y2 = req("PATCH", f"/yamls/{yid}", {"title": "测试片段改名"})
    check("PATCH YAML", st == 200 and y2["title"] == "测试片段改名")
    st, _ = req("DELETE", f"/yamls/{yid}")
    check("DELETE YAML", st == 200)

    # ---------- 10 审计日志 ----------
    st, a1 = req("GET", "/audit?limit=300")
    check("审计日志返回 200", st == 200)
    kinds = {x["action"] for x in (a1 or [])}
    check("审计含 create", "create" in kinds)
    check("审计含 update", "update" in kinds)
    check("审计含 delete", "delete" in kinds)
    check("审计含 transition", "transition" in kinds)
    check("审计含 import 或 seed", ("import" in kinds) or ("seed" in kinds))

    # ---------- 11 导出 / 导入 ----------
    st, ex = req("GET", "/io/export")
    check("导出全库", st == 200 and len(ex.get("nodes", [])) >= 41, f"导出节点 {len(ex.get('nodes', []))}")
    check("导出含知识/SOP/YAML", bool(ex.get("notes")) and bool(ex.get("sops")) and bool(ex.get("yamls")))
    st, im = req("POST", "/io/import?mode=merge", ex)
    ok_import = st == 200 and isinstance(im, dict) and im.get("imported", {}).get("nodes", 0) >= 41
    check("导入(merge) 回灌自身", ok_import, str(im)[:200] if not ok_import else str(im.get("imported")))

    # ---------- 清理测试数据 ----------
    req("DELETE", "/edges/zz-test-node->pod")
    st, _ = req("DELETE", "/nodes/zz-test-node")
    check("清理：删除测试组件", st == 200)
    st, after = req("GET", "/health")
    check("清理后组件数回到 41", after["counts"]["nodes"] == 41, f"实际 {after['counts']['nodes']}")
    check("清理后关系数回到 42", after["counts"]["edges"] == 42, f"实际 {after['counts']['edges']}")

    # ---------- 汇总 ----------
    print("\n" + "=" * 60)
    print(f"PASS {len(PASS)}   FAIL {len(FAIL)}")
    if FAIL:
        print("失败项：")
        for f in FAIL:
            print("  - " + f)
    print("=" * 60)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
