"""图谱读接口与种子数据的测试。"""
from __future__ import annotations


def test_graph_shape(client):
    g = client.get("/api/atlas/graph").json()
    assert len(g["layers"]) == 8
    assert len(g["groups"]) == 8
    assert len(g["nodes"]) == 41
    assert len(g["edges"]) == 42


def test_graph_nodes_have_fields(client):
    g = client.get("/api/atlas/graph").json()
    with_fields = [n for n in g["nodes"] if n.get("fields")]
    assert len(with_fields) >= 1
    n = with_fields[0]
    assert "label" in n["fields"][0] and "value" in n["fields"][0]


def test_graph_group_ordinals_skip_six(client):
    """分组编号忠实还原参考图：①~⑤ 之后直接 ⑦。"""
    g = client.get("/api/atlas/graph").json()
    ords = [x["ordinal"] for x in g["groups"]]
    assert ords == ["①", "②", "③", "④", "⑤", "⑦", "⑧", "⑨"]


def test_health_counts(client):
    d = client.get("/api/health").json()
    assert d["status"] == "ok"
    assert d["counts"]["nodes"] == 41
    assert d["counts"]["users"] >= 1


def test_search_hits_node(client):
    r = client.get("/api/atlas/search", params={"q": "apiserver"}).json()
    assert r["total"] >= 1
    assert any(i["id"] == "apiserver" for i in r["items"])


def test_search_chinese(client):
    """中文检索：'策略' 能命中 kind 为「策略组件」的 NetworkPolicy 等。"""
    r = client.get("/api/atlas/search", params={"q": "策略"}).json()
    assert r["total"] >= 1
    assert any(i["id"] == "netpol" for i in r["items"]), r["items"]


def test_search_no_result(client):
    r = client.get("/api/atlas/search", params={"q": "zzz-not-exist-zzz"}).json()
    assert r["total"] == 0


def test_search_requires_q(client):
    assert client.get("/api/atlas/search").status_code == 422


def test_views_list(client):
    vs = client.get("/api/atlas/views").json()
    ids = [v["id"] for v in vs]
    assert "all" in ids and "network" in ids
    net = [v for v in vs if v["id"] == "network"][0]
    assert set(net["target_groups"]) == {"g3", "g4"}


def test_node_detail_404(client):
    assert client.get("/api/nodes/no-such-node").status_code == 404


def test_node_detail(client):
    n = client.get("/api/nodes/netpol").json()
    assert n["id"] == "netpol"
    assert n["layer_id"] == "policy"
    assert any(f["value"] == "ALLOW / DENY" for f in n["fields"])


def test_layers_list(client):
    ls = client.get("/api/layers").json()
    assert len(ls) == 8
    colors = {l["color"] for l in ls}
    assert len(colors) == 8                       # 8 个分类颜色互不重复


def test_seed_notes_and_sops(client):
    notes = client.get("/api/notes").json()
    assert len(notes) >= 3
    assert any(t["slug"] == "networkpolicy-basics" for t in notes)
    sops = client.get("/api/sops").json()
    assert len(sops) >= 2
    svc = [s for s in sops if s["symptom"] == "service-502"][0]
    assert len(svc["steps"]) >= 4                 # SOP 步骤已落库
