"""写操作（CRUD）、状态流转、审计、导入导出的测试。"""
from __future__ import annotations

NODE = {
    "id": "t_node", "group_id": "g3", "layer_id": "policy",
    "name": "测试组件", "kind": "测试类型", "summary": "一句话",
    "cmd": "kubectl get pods", "x": 100, "y": 200,
    "fields": [{"label": "端口", "value": "8443"}],
}


# ---------- 组件 CRUD ----------


def test_create_node(admin_client):
    r = admin_client.post("/api/nodes", json=NODE)
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "测试组件"
    assert body["fields"][0]["value"] == "8443"
    admin_client.delete("/api/nodes/t_node")


def test_create_node_conflict_409(admin_client):
    admin_client.post("/api/nodes", json=NODE)
    r = admin_client.post("/api/nodes", json=NODE)
    assert r.status_code == 409
    admin_client.delete("/api/nodes/t_node")


def test_create_node_bad_group_400(admin_client):
    r = admin_client.post("/api/nodes", json={**NODE, "id": "t_bad", "group_id": "no-such"})
    assert r.status_code == 400


def test_create_node_missing_field_422(admin_client):
    r = admin_client.post("/api/nodes", json={"id": "x", "group_id": "g3", "layer_id": "policy"})
    assert r.status_code == 422


def test_patch_node(admin_client):
    admin_client.post("/api/nodes", json=NODE)
    r = admin_client.patch("/api/nodes/t_node", json={"summary": "改过了", "x": 999})
    assert r.status_code == 200
    assert r.json()["summary"] == "改过了"
    assert r.json()["x"] == 999
    assert admin_client.get("/api/nodes/t_node").json()["summary"] == "改过了"
    admin_client.delete("/api/nodes/t_node")


def test_patch_node_empty_body_400(admin_client):
    admin_client.post("/api/nodes", json=NODE)
    assert admin_client.patch("/api/nodes/t_node", json={}).status_code == 400
    admin_client.delete("/api/nodes/t_node")


def test_patch_node_fields_replace(admin_client):
    admin_client.post("/api/nodes", json=NODE)
    r = admin_client.patch("/api/nodes/t_node", json={"fields": [{"label": "新", "value": "值"}]})
    fs = r.json()["fields"]
    assert len(fs) == 1 and fs[0]["label"] == "新"
    admin_client.delete("/api/nodes/t_node")


def test_delete_node_404_after(admin_client):
    admin_client.post("/api/nodes", json=NODE)
    assert admin_client.delete("/api/nodes/t_node").status_code == 200
    assert admin_client.get("/api/nodes/t_node").status_code == 404


def test_delete_node_cascades_edges(admin_client):
    admin_client.post("/api/nodes", json=NODE)
    admin_client.post("/api/edges", json={"from_node": "t_node", "to_node": "pod", "label": "测试"})
    assert admin_client.get("/api/edges/t_node->pod").status_code == 200
    admin_client.delete("/api/nodes/t_node")
    assert admin_client.get("/api/edges/t_node->pod").status_code == 404


def test_delete_node_nulls_related_note(admin_client):
    """删除组件后，关联知识条目的 node_id 由外键置空，条目本身保留。"""
    admin_client.post("/api/nodes", json=NODE)
    admin_client.post("/api/notes", json={
        "slug": "t_note", "node_id": "t_node", "title": "关联", "markdown": "x",
    })
    admin_client.delete("/api/nodes/t_node")
    n = admin_client.get("/api/notes/t_note").json()
    assert n["node_id"] is None
    assert n["title"] == "关联"
    admin_client.delete("/api/notes/t_note")


# ---------- 关系 CRUD ----------


def test_create_edge_auto_id(admin_client):
    r = admin_client.post("/api/edges", json={"from_node": "pod", "to_node": "service", "label": "测试"})
    assert r.status_code == 201
    assert r.json()["id"] == "pod->service"
    admin_client.delete("/api/edges/pod->service")


def test_create_edge_bad_node_400(admin_client):
    r = admin_client.post("/api/edges", json={"from_node": "ghost", "to_node": "pod"})
    assert r.status_code == 400


def test_delete_edge(admin_client):
    admin_client.post("/api/edges", json={"id": "t_edge", "from_node": "pod", "to_node": "service"})
    assert admin_client.delete("/api/edges/t_edge").status_code == 200
    assert admin_client.get("/api/edges/t_edge").status_code == 404


# ---------- 分组 ----------


def test_group_crud_and_force_delete(admin_client):
    g = {"id": "t_grp", "ordinal": "⑩", "title": "临时分组", "subtitle": "", "x": 1, "y": 1, "w": 100, "h": 100}
    assert admin_client.post("/api/groups", json=g).status_code == 201
    assert admin_client.patch("/api/groups/t_grp", json={"title": "改名"}).json()["title"] == "改名"
    # 非空分组不能直接删
    admin_client.post("/api/nodes", json={**NODE, "id": "t_in_grp", "group_id": "t_grp", "x": 2, "y": 2})
    assert admin_client.delete("/api/groups/t_grp").status_code == 409
    # force + move_to
    r = admin_client.delete("/api/groups/t_grp?force=true&move_to=g3")
    assert r.status_code == 200
    assert r.json()["moved_to"] == "g3"
    assert admin_client.get("/api/nodes/t_in_grp").json()["group_id"] == "g3"
    admin_client.delete("/api/nodes/t_in_grp")


def test_group_force_delete_bad_target_400(admin_client):
    admin_client.post("/api/groups", json={
        "id": "t_grp2", "ordinal": "⑪", "title": "x", "x": 1, "y": 1, "w": 10, "h": 10,
    })
    admin_client.post("/api/nodes", json={**NODE, "id": "t_in_grp2", "group_id": "t_grp2", "x": 2, "y": 2})
    r = admin_client.delete("/api/groups/t_grp2?force=true&move_to=no-such")
    assert r.status_code == 400
    # 分组与组件都不动
    assert admin_client.get("/api/groups/t_grp2").status_code == 200
    assert admin_client.get("/api/nodes/t_in_grp2").json()["group_id"] == "t_grp2"
    admin_client.delete("/api/nodes/t_in_grp2")
    admin_client.delete("/api/groups/t_grp2")


# ---------- 知识条目与状态流转 ----------


def test_note_crud(admin_client):
    r = admin_client.post("/api/notes", json={
        "slug": "t_note2", "title": "临时", "markdown": "# 标题\n正文", "status": "draft",
    })
    assert r.status_code == 201 and r.json()["status"] == "draft"
    assert admin_client.patch("/api/notes/t_note2", json={"title": "改"}).json()["title"] == "改"
    assert admin_client.delete("/api/notes/t_note2").status_code == 200


def test_note_transition_happy_path(admin_client):
    admin_client.post("/api/notes", json={"slug": "t_flow", "title": "流", "markdown": ""})
    r = admin_client.post("/api/notes/t_flow/transition", json={"action": "publish"})
    assert r.status_code == 200 and r.json()["status"] == "review"
    r = admin_client.post("/api/notes/t_flow/transition", json={"action": "approve"})
    assert r.json()["status"] == "published"
    r = admin_client.post("/api/notes/t_flow/transition", json={"action": "archive"})
    assert r.json()["status"] == "archived"
    r = admin_client.post("/api/notes/t_flow/transition", json={"action": "restore"})
    assert r.json()["status"] == "draft"
    admin_client.delete("/api/notes/t_flow")


def test_note_illegal_transition_400(admin_client):
    admin_client.post("/api/notes", json={"slug": "t_flow2", "title": "流", "markdown": ""})
    # draft 不能直接 approve
    assert admin_client.post("/api/notes/t_flow2/transition", json={"action": "approve"}).status_code == 400
    admin_client.post("/api/notes/t_flow2/transition", json={"action": "publish"})
    # review 不能再次 publish
    assert admin_client.post("/api/notes/t_flow2/transition", json={"action": "publish"}).status_code == 400
    admin_client.delete("/api/notes/t_flow2")


def test_note_unknown_action_422(admin_client):
    admin_client.post("/api/notes", json={"slug": "t_flow3", "title": "流", "markdown": ""})
    r = admin_client.post("/api/notes/t_flow3/transition", json={"action": "delete-everything"})
    assert r.status_code == 422
    admin_client.delete("/api/notes/t_flow3")


def test_sop_crud_and_transition(admin_client):
    r = admin_client.post("/api/sops", json={
        "symptom": "t_sop", "title": "临时 SOP",
        "steps": [{"step_no": 1, "action": "看事件", "expect": "有原因", "command": "kubectl describe pod"}],
    })
    assert r.status_code == 201 and len(r.json()["steps"]) == 1
    r = admin_client.post("/api/sops/t_sop/transition", json={"action": "publish"})
    assert r.json()["status"] == "review"
    r = admin_client.post("/api/sops/t_sop/transition", json={"action": "approve"})
    assert r.json()["status"] == "published"
    # 改步骤
    r = admin_client.patch("/api/sops/t_sop", json={"steps": []})
    assert r.json()["steps"] == []
    assert admin_client.delete("/api/sops/t_sop").status_code == 200


# ---------- YAML ----------


def test_yaml_crud(admin_client):
    r = admin_client.post("/api/yamls", json={"node_id": "pod", "title": "临时片段", "yaml": "kind: Pod"})
    assert r.status_code == 201
    yid = r.json()["id"]
    assert admin_client.patch(f"/api/yamls/{yid}", json={"title": "改"}).json()["title"] == "改"
    assert admin_client.delete(f"/api/yamls/{yid}").status_code == 200
    assert admin_client.get(f"/api/yamls/{yid}").status_code == 404


# ---------- 审计 ----------


def test_audit_records_actor(admin_client):
    admin_client.post("/api/nodes", json=NODE)
    logs = admin_client.get("/api/audit", params={"limit": 50}).json()
    mine = [x for x in logs if x["entity_id"] == "t_node"]
    assert len(mine) >= 1
    assert all(x["actor"] == "admin" for x in mine), mine
    admin_client.delete("/api/nodes/t_node")


def test_audit_filter_by_entity(admin_client):
    logs = admin_client.get("/api/audit", params={"entity": "node", "limit": 20}).json()
    assert all(x["entity"] == "node" for x in logs)


def test_audit_filter_by_actor(admin_client):
    logs = admin_client.get("/api/audit", params={"actor": "admin", "limit": 20}).json()
    assert all(x["actor"] == "admin" for x in logs)


# ---------- 导入导出 ----------


def test_export_shape(admin_client):
    ex = admin_client.get("/api/io/export").json()
    for key in ("layers", "groups", "nodes", "edges", "notes", "sops", "yamls"):
        assert key in ex and isinstance(ex[key], list)
    assert len(ex["nodes"]) >= 41


def test_import_rejects_non_list_422(admin_client):
    assert admin_client.post("/api/io/import?mode=merge", json={"nodes": "not-a-list"}).status_code == 422
    assert admin_client.post("/api/io/import?mode=merge", json={"layers": 123}).status_code == 422


def test_import_bad_mode_422(admin_client):
    assert admin_client.post("/api/io/import?mode=destroy", json={}).status_code == 422


def test_import_merge_roundtrip(admin_client):
    ex = admin_client.get("/api/io/export").json()
    r = admin_client.post("/api/io/import?mode=merge", json=ex)
    assert r.status_code == 200
    assert r.json()["imported"]["nodes"] >= 41


def test_import_replace_rolls_back_on_error(admin_client):
    """replace 导入失败必须整体回滚，不能丢原数据。"""
    before = admin_client.get("/api/health").json()["counts"]["nodes"]
    ex = admin_client.get("/api/io/export").json()
    ex["nodes"] = ex["nodes"] + [{
        "id": "t_bad", "group_id": "no-such-group", "layer_id": "policy",
        "name": "坏", "kind": "", "summary": "", "cmd": "", "x": 0, "y": 0, "fields": [],
    }]
    r = admin_client.post("/api/io/import?mode=replace", json=ex)
    assert r.status_code == 400
    assert "回滚" in r.json()["detail"]
    after = admin_client.get("/api/health").json()["counts"]["nodes"]
    assert before == after
    assert admin_client.get("/api/nodes/apiserver").status_code == 200
