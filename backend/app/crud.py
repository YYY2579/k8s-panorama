"""全部数据库读写逻辑。

约定：
- 这是**唯一**写库的地方，路由层只做参数校验 + 调用这里。
- 每个写操作都会写一条 audit_log，保证任何变更可追溯。
- 所有函数接收 `db: Session` 并在内部 commit（出错自行 rollback 并抛 HTTPException）。
"""
from __future__ import annotations

import json
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import DateTime, func, or_, select
from sqlalchemy.orm import Session, selectinload

from . import models


def _utcnow():
    """naive UTC。SQLite 的 DateTime 列不保存时区，aware/naive 混用会在比较时抛
    TypeError，因此与 models._now() 保持同一种表示（详见 D3 审查项）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ------------------------------------------------------------------ 审计
# 当前操作者。由路由层在函数体内调用 set_actor() 设置。
# 注意：不能用 FastAPI 的 generator 依赖来设置 —— 同步依赖的 __enter__ 与路由函数体
# 分别在两次 to_thread 调用里执行，ContextVar 的修改不会跨调用传递（实测 actor 全是 anonymous）。
current_actor: ContextVar[str] = ContextVar("atlas_current_actor", default="anonymous")


def set_actor(name: str) -> None:
    """记录本次请求的操作者。必须在路由函数体第一行调用（与 audit 同一次线程执行）。"""
    current_actor.set(name)


def audit(
    db: Session,
    action: str,
    entity: str,
    entity_id: str,
    detail: str = "",
    actor: str | None = None,
) -> models.AuditLog:
    """写审计日志。actor 不传则取 current_actor（路由层已设置）。"""
    who = actor if actor is not None else current_actor.get()
    row = models.AuditLog(
        action=action, entity=entity, entity_id=str(entity_id), detail=detail, actor=who
    )
    db.add(row)
    return row


def list_audit(
    db: Session,
    limit: int = 50,
    entity: str | None = None,
    actor: str | None = None,
) -> list[models.AuditLog]:
    stmt = select(models.AuditLog).order_by(models.AuditLog.id.desc()).limit(limit)
    if entity:
        stmt = stmt.where(models.AuditLog.entity == entity)
    if actor:
        stmt = stmt.where(models.AuditLog.actor == actor)
    return list(db.scalars(stmt).all())


# ------------------------------------------------------------------ 图层
def list_layers(db: Session) -> list[models.Layer]:
    return list(db.scalars(select(models.Layer).order_by(models.Layer.sort_order)).all())


def get_layer(db: Session, layer_id: str) -> models.Layer:
    obj = db.get(models.Layer, layer_id)
    if not obj:
        raise HTTPException(404, f"图层不存在：{layer_id}")
    return obj


def patch_layer(db: Session, layer_id: str, data: dict[str, Any]) -> models.Layer:
    obj = get_layer(db, layer_id)
    for k, v in data.items():
        if v is not None:
            setattr(obj, k, v)
    audit(db, "update", "layer", layer_id, json.dumps(data, ensure_ascii=False, default=str))
    db.commit()
    db.refresh(obj)
    return obj


# ------------------------------------------------------------------ 分组
def list_groups(db: Session) -> list[models.Group]:
    return list(db.scalars(select(models.Group).order_by(models.Group.sort_order)).all())


def get_group(db: Session, group_id: str) -> models.Group:
    obj = db.get(models.Group, group_id)
    if not obj:
        raise HTTPException(404, f"分组不存在：{group_id}")
    return obj


def create_group(db: Session, data: dict[str, Any]) -> models.Group:
    if db.get(models.Group, data["id"]):
        raise HTTPException(409, f"分组已存在：{data['id']}")
    obj = models.Group(**data)
    db.add(obj)
    audit(db, "create", "group", data["id"], json.dumps(data, ensure_ascii=False))
    db.commit()
    db.refresh(obj)
    return obj


def update_group(db: Session, group_id: str, data: dict[str, Any]) -> models.Group:
    obj = get_group(db, group_id)
    for k, v in data.items():
        if v is not None:
            setattr(obj, k, v)
    audit(db, "update", "group", group_id, json.dumps(data, ensure_ascii=False, default=str))
    db.commit()
    db.refresh(obj)
    return obj


def delete_group(db: Session, group_id: str, force: bool = False, move_to: str | None = None) -> dict:
    """删除分组。

    force=True 时把该分组下的组件搬到 move_to 指定的分组（不传则用排序第一个的其它分组，
    并在返回值里说明去向），避免外键悬空。目标分组必须显式存在，不接隐式猜测。
    """
    obj = get_group(db, group_id)
    used = db.scalar(select(func.count()).select_from(models.Node).where(models.Node.group_id == group_id))
    if used and not force:
        raise HTTPException(409, f"该分组下还有 {used} 个组件，请先移走或用 force 并指定 move_to")
    if used:
        if move_to:
            target = move_to
            if not db.get(models.Group, target):
                raise HTTPException(400, f"目标分组不存在：{target}")
        else:
            other = db.scalars(select(models.Group).where(models.Group.id != group_id)).first()
            if not other:
                raise HTTPException(409, "无法强制删除：系统至少要保留一个分组")
            target = other.id
        db.execute(
            models.Node.__table__.update()
            .where(models.Node.group_id == group_id)
            .values(group_id=target)
        )
        audit(db, "move", "node", "-", f"{used} 个组件从 {group_id} 移至 {target}")
    db.delete(obj)
    audit(db, "delete", "group", group_id, f"force={force}" + (f" move_to={target}" if used else ""))
    db.commit()
    return {"deleted": 1, "id": group_id, "moved_nodes": used if force else 0, "moved_to": target if used else None}


# ------------------------------------------------------------------ 组件
def list_nodes(db: Session, group_id: str | None = None, layer_id: str | None = None) -> list[models.Node]:
    stmt = select(models.Node).options(selectinload(models.Node.fields)).order_by(
        models.Node.group_id, models.Node.y, models.Node.x
    )
    if group_id:
        stmt = stmt.where(models.Node.group_id == group_id)
    if layer_id:
        stmt = stmt.where(models.Node.layer_id == layer_id)
    return list(db.scalars(stmt).all())


def get_node(db: Session, node_id: str) -> models.Node:
    obj = db.scalar(
        select(models.Node).options(selectinload(models.Node.fields)).where(models.Node.id == node_id)
    )
    if not obj:
        raise HTTPException(404, f"组件不存在：{node_id}")
    return obj


def create_node(db: Session, data: dict[str, Any]) -> models.Node:
    if db.get(models.Node, data["id"]):
        raise HTTPException(409, f"组件已存在：{data['id']}")
    if not db.get(models.Group, data["group_id"]):
        raise HTTPException(400, f"分组不存在：{data['group_id']}")
    if not db.get(models.Layer, data["layer_id"]):
        raise HTTPException(400, f"图层不存在：{data['layer_id']}")
    fields = data.pop("fields", []) or []
    obj = models.Node(**data)
    obj.fields = [
        models.NodeField(label=f.get("label", ""), value=f.get("value", ""), sort_order=i)
        for i, f in enumerate(fields)
    ]
    db.add(obj)
    audit(db, "create", "node", data["id"], json.dumps({"name": data.get("name"), "fields": fields}, ensure_ascii=False))
    db.commit()
    db.refresh(obj)
    return obj


def update_node(db: Session, node_id: str, data: dict[str, Any]) -> models.Node:
    obj = get_node(db, node_id)
    fields = data.pop("fields", None)
    if data.get("group_id") and not db.get(models.Group, data["group_id"]):
        raise HTTPException(400, f"分组不存在：{data['group_id']}")
    if data.get("layer_id") and not db.get(models.Layer, data["layer_id"]):
        raise HTTPException(400, f"图层不存在：{data['layer_id']}")
    for k, v in data.items():
        if v is not None:
            setattr(obj, k, v)
    if fields is not None:  # 传了就整体替换（含 [] 清空）
        obj.fields = [
            models.NodeField(label=f.get("label", ""), value=f.get("value", ""), sort_order=i)
            for i, f in enumerate(fields)
        ]
    obj.updated_at = _utcnow()
    audit(db, "update", "node", node_id, json.dumps(data, ensure_ascii=False, default=str))
    db.commit()
    db.refresh(obj)
    return obj


def delete_node(db: Session, node_id: str) -> dict:
    obj = get_node(db, node_id)
    # Edge / NodeField 由 ORM cascade 删除；
    # Note / YamlSnippet 的 node_id 由外键 ondelete="SET NULL" 自动置空
    # （db.py 的连接钩子已开启 PRAGMA foreign_keys=ON），无需手工 UPDATE
    db.delete(obj)
    audit(db, "delete", "node", node_id, obj.name)
    db.commit()
    return {"deleted": 1, "id": node_id}


# ------------------------------------------------------------------ 关系
def list_edges(db: Session) -> list[models.Edge]:
    return list(db.scalars(select(models.Edge).order_by(models.Edge.sort_order)).all())


def get_edge(db: Session, edge_id: str) -> models.Edge:
    obj = db.get(models.Edge, edge_id)
    if not obj:
        raise HTTPException(404, f"关系不存在：{edge_id}")
    return obj


def create_edge(db: Session, data: dict[str, Any]) -> models.Edge:
    for key in ("from_node", "to_node"):
        if not db.get(models.Node, data[key]):
            raise HTTPException(400, f"组件不存在：{data[key]}")
    eid = data.get("id") or f"{data['from_node']}->{data['to_node']}"
    if db.get(models.Edge, eid):
        raise HTTPException(409, f"关系已存在：{eid}")
    obj = models.Edge(
        id=eid,
        from_node=data["from_node"],
        to_node=data["to_node"],
        label=data.get("label", ""),
        layer_id=data.get("layer_id"),
        sort_order=data.get("sort_order", 0),
    )
    db.add(obj)
    audit(db, "create", "edge", eid, f"{obj.from_node} → {obj.to_node} ({obj.label})")
    db.commit()
    db.refresh(obj)
    return obj


def update_edge(db: Session, edge_id: str, data: dict[str, Any]) -> models.Edge:
    obj = get_edge(db, edge_id)
    for k, v in data.items():
        if v is not None:
            setattr(obj, k, v)
    audit(db, "update", "edge", edge_id, json.dumps(data, ensure_ascii=False, default=str))
    db.commit()
    db.refresh(obj)
    return obj


def delete_edge(db: Session, edge_id: str) -> dict:
    obj = get_edge(db, edge_id)
    db.delete(obj)
    audit(db, "delete", "edge", edge_id, f"{obj.from_node} → {obj.to_node}")
    db.commit()
    return {"deleted": 1, "id": edge_id}


# ------------------------------------------------------------------ 知识条目
STATUS_FLOW = {
    "publish": ("draft", "review"),
    "approve": ("review", "published"),
    "archive": (None, "archived"),     # 任意状态
    "restore": ("archived", "draft"),
}


def list_notes(db: Session, status: str | None = None, node_id: str | None = None) -> list[models.Note]:
    stmt = select(models.Note).order_by(models.Note.updated_at.desc())
    if status:
        stmt = stmt.where(models.Note.status == status)
    if node_id:
        stmt = stmt.where(models.Note.node_id == node_id)
    return list(db.scalars(stmt).all())


def get_note(db: Session, slug: str) -> models.Note:
    obj = db.get(models.Note, slug)
    if not obj:
        raise HTTPException(404, f"知识条目不存在：{slug}")
    return obj


def create_note(db: Session, data: dict[str, Any]) -> models.Note:
    if db.get(models.Note, data["slug"]):
        raise HTTPException(409, f"知识条目已存在：{data['slug']}")
    obj = models.Note(**data)
    db.add(obj)
    audit(db, "create", "note", data["slug"], data.get("title", ""))
    db.commit()
    db.refresh(obj)
    return obj


def update_note(db: Session, slug: str, data: dict[str, Any]) -> models.Note:
    obj = get_note(db, slug)
    for k, v in data.items():
        if v is not None:
            setattr(obj, k, v)
    obj.updated_at = _utcnow()
    audit(db, "update", "note", slug, json.dumps(data, ensure_ascii=False, default=str))
    db.commit()
    db.refresh(obj)
    return obj


def delete_note(db: Session, slug: str) -> dict:
    obj = get_note(db, slug)
    db.delete(obj)
    audit(db, "delete", "note", slug, obj.title)
    db.commit()
    return {"deleted": 1, "id": slug}


def transition_note(db: Session, slug: str, action: str, comment: str = "") -> models.Note:
    obj = get_note(db, slug)
    expect_from, to = STATUS_FLOW[action]
    if expect_from is not None and obj.status != expect_from:
        raise HTTPException(400, f"当前状态为 {obj.status}，不能执行 {action}（需要 {expect_from}）")
    if obj.status == to:
        raise HTTPException(400, f"已经处于 {to} 状态")
    old = obj.status
    obj.status = to
    obj.updated_at = _utcnow()
    audit(db, "transition", "note", slug, f"{old} --{action}--> {to} {comment}".strip())
    db.commit()
    db.refresh(obj)
    return obj


# ------------------------------------------------------------------ 排障 SOP
def list_sops(db: Session, status: str | None = None) -> list[models.Sop]:
    stmt = select(models.Sop).order_by(models.Sop.updated_at.desc())
    if status:
        stmt = stmt.where(models.Sop.status == status)
    return list(db.scalars(stmt).all())


def get_sop(db: Session, symptom: str) -> models.Sop:
    obj = db.get(models.Sop, symptom)
    if not obj:
        raise HTTPException(404, f"排障 SOP 不存在：{symptom}")
    return obj


def create_sop(db: Session, data: dict[str, Any]) -> models.Sop:
    if db.get(models.Sop, data["symptom"]):
        raise HTTPException(409, f"排障 SOP 已存在：{data['symptom']}")
    steps = data.pop("steps", []) or []
    obj = models.Sop(**data)
    obj.steps = [models.SopStep(**s) for s in steps]
    db.add(obj)
    audit(db, "create", "sop", data["symptom"], data.get("title", ""))
    db.commit()
    db.refresh(obj)
    return obj


def update_sop(db: Session, symptom: str, data: dict[str, Any]) -> models.Sop:
    obj = get_sop(db, symptom)
    steps = data.pop("steps", None)
    for k, v in data.items():
        if v is not None:
            setattr(obj, k, v)
    if steps is not None:
        obj.steps = [models.SopStep(**s) for s in steps]
    obj.updated_at = _utcnow()
    audit(db, "update", "sop", symptom, json.dumps(data, ensure_ascii=False, default=str))
    db.commit()
    db.refresh(obj)
    return obj


def delete_sop(db: Session, symptom: str) -> dict:
    obj = get_sop(db, symptom)
    db.delete(obj)
    audit(db, "delete", "sop", symptom, obj.title)
    db.commit()
    return {"deleted": 1, "id": symptom}


def transition_sop(db: Session, symptom: str, action: str, comment: str = "") -> models.Sop:
    obj = get_sop(db, symptom)
    expect_from, to = STATUS_FLOW[action]
    if expect_from is not None and obj.status != expect_from:
        raise HTTPException(400, f"当前状态为 {obj.status}，不能执行 {action}（需要 {expect_from}）")
    if obj.status == to:
        raise HTTPException(400, f"已经处于 {to} 状态")
    old = obj.status
    obj.status = to
    obj.updated_at = _utcnow()
    audit(db, "transition", "sop", symptom, f"{old} --{action}--> {to} {comment}".strip())
    db.commit()
    db.refresh(obj)
    return obj


# ------------------------------------------------------------------ YAML
def list_yamls(db: Session, node_id: str | None = None) -> list[models.YamlSnippet]:
    stmt = select(models.YamlSnippet).order_by(models.YamlSnippet.id)
    if node_id:
        stmt = stmt.where(models.YamlSnippet.node_id == node_id)
    return list(db.scalars(stmt).all())


def get_yaml(db: Session, yaml_id: int) -> models.YamlSnippet:
    obj = db.get(models.YamlSnippet, yaml_id)
    if not obj:
        raise HTTPException(404, f"YAML 片段不存在：{yaml_id}")
    return obj


def create_yaml(db: Session, data: dict[str, Any]) -> models.YamlSnippet:
    obj = models.YamlSnippet(**data)
    db.add(obj)
    db.flush()
    audit(db, "create", "yaml", str(obj.id), data.get("title", ""))
    db.commit()
    db.refresh(obj)
    return obj


def update_yaml(db: Session, yaml_id: int, data: dict[str, Any]) -> models.YamlSnippet:
    obj = get_yaml(db, yaml_id)
    for k, v in data.items():
        if v is not None:
            setattr(obj, k, v)
    audit(db, "update", "yaml", str(yaml_id), json.dumps(data, ensure_ascii=False, default=str))
    db.commit()
    db.refresh(obj)
    return obj


def delete_yaml(db: Session, yaml_id: int) -> dict:
    obj = get_yaml(db, yaml_id)
    db.delete(obj)
    audit(db, "delete", "yaml", str(yaml_id), obj.title)
    db.commit()
    return {"deleted": 1, "id": yaml_id}


# ------------------------------------------------------------------ 搜索
def search(db: Session, q: str, limit: int = 20) -> list[dict]:
    """跨组件 / 知识 / SOP 检索（SQLite 用 LIKE，够用且无额外依赖）。"""
    kw = f"%{q.strip()}%"
    items: list[dict] = []

    nodes = db.scalars(
        select(models.Node)
        .where(
            or_(
                models.Node.name.ilike(kw),
                models.Node.kind.ilike(kw),
                models.Node.summary.ilike(kw),
                models.Node.cmd.ilike(kw),
                models.Node.id.ilike(kw),
            )
        )
        .limit(limit)
    ).all()
    for n in nodes:
        items.append({"type": "node", "id": n.id, "title": n.name, "subtitle": n.kind, "node_id": n.id})

    notes = db.scalars(
        select(models.Note)
        .where(or_(models.Note.title.ilike(kw), models.Note.markdown.ilike(kw), models.Note.slug.ilike(kw)))
        .limit(limit)
    ).all()
    for t in notes:
        items.append({"type": "note", "id": t.slug, "title": t.title, "subtitle": t.status, "node_id": t.node_id})

    sops = db.scalars(
        select(models.Sop)
        .where(or_(models.Sop.symptom.ilike(kw), models.Sop.title.ilike(kw)))
        .limit(limit)
    ).all()
    for s in sops:
        items.append({"type": "sop", "id": s.symptom, "title": s.title, "subtitle": s.status, "node_id": None})

    return items[:limit]


# ------------------------------------------------------------------ 导出 / 导入
def export_all(db: Session) -> dict:
    return {
        "version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "layers": [
            {c.name: getattr(o, c.name) for c in models.Layer.__table__.columns}
            for o in list_layers(db)
        ],
        "groups": [
            {c.name: getattr(o, c.name) for c in models.Group.__table__.columns}
            for o in list_groups(db)
        ],
        "nodes": [
            {
                **{c.name: getattr(o, c.name) for c in models.Node.__table__.columns},
                "fields": [{"label": f.label, "value": f.value} for f in o.fields],
            }
            for o in list_nodes(db)
        ],
        "edges": [
            {c.name: getattr(o, c.name) for c in models.Edge.__table__.columns}
            for o in list_edges(db)
        ],
        "notes": [
            {c.name: getattr(o, c.name) for c in models.Note.__table__.columns}
            for o in list_notes(db)
        ],
        "sops": [
            {
                **{c.name: getattr(o, c.name) for c in models.Sop.__table__.columns},
                "steps": [
                    {"step_no": s.step_no, "action": s.action, "expect": s.expect, "command": s.command}
                    for s in o.steps
                ],
            }
            for o in list_sops(db)
        ],
        "yamls": [
            {c.name: getattr(o, c.name) for c in models.YamlSnippet.__table__.columns}
            for o in list_yamls(db)
        ],
    }


def _coerce_row(model, row: dict) -> dict:
    """只保留模型存在的列，并把 ISO 时间字符串还原成 datetime（SQLite 不接受字符串写 DateTime 列）。"""
    out = {}
    for c in model.__table__.columns:
        if c.name not in row:
            continue
        v = row[c.name]
        if isinstance(v, str) and isinstance(c.type, DateTime):
            try:
                v = datetime.fromisoformat(v)
            except ValueError:
                v = _utcnow()
        out[c.name] = v
    return out


def import_all(db: Session, payload: dict, mode: str = "merge") -> dict:
    """导入 JSON 到库。

    mode=replace  —— 先清空业务表再导入
    mode=merge    —— 已存在则更新，不存在则新建

    整个导入（含 replace 的清空）在同一个事务里：全部成功才提交，
    任一步失败整体回滚，不会出现"清空已落库、导入却失败"导致的数据丢失。
    """
    stats = {"layers": 0, "groups": 0, "nodes": 0, "edges": 0, "notes": 0, "sops": 0, "yamls": 0}

    try:
        if mode == "replace":
            # 先子表后父表，避免外键冲突
            for table in (
                models.SopStep, models.Sop, models.Note, models.YamlSnippet,
                models.Edge, models.NodeField, models.Node, models.Group, models.Layer,
            ):
                db.execute(table.__table__.delete())
            db.flush()

        def _merge(model, pk, rows):
            n = 0
            for row in rows:
                row = _coerce_row(model, row)
                if pk not in row:
                    continue
                obj = db.get(model, row[pk])
                if obj is None:
                    db.add(model(**row))
                else:
                    for k, v in row.items():
                        if k != pk:
                            setattr(obj, k, v)
                n += 1
            db.flush()          # 循环外统一 flush 一次，减少语句往返
            return n

        stats["layers"] = _merge(models.Layer, "id", payload.get("layers", []))
        stats["groups"] = _merge(models.Group, "id", payload.get("groups", []))
        stats["notes"] = _merge(models.Note, "slug", payload.get("notes", []))
        stats["edges"] = _merge(models.Edge, "id", payload.get("edges", []))
        stats["yamls"] = _merge(models.YamlSnippet, "id", payload.get("yamls", []))

        for row in payload.get("nodes", []):
            fields = row.pop("fields", [])
            row = _coerce_row(models.Node, row)
            obj = db.get(models.Node, row["id"])
            if obj is None:
                obj = models.Node(**row)
                db.add(obj)
            else:
                for k, v in row.items():
                    if k != "id":
                        setattr(obj, k, v)
                obj.fields.clear()
            obj.fields = [
                models.NodeField(label=f.get("label", ""), value=f.get("value", ""), sort_order=i)
                for i, f in enumerate(fields)
            ]
            stats["nodes"] += 1
        db.flush()

        for row in payload.get("sops", []):
            steps = row.pop("steps", [])
            row = _coerce_row(models.Sop, row)
            obj = db.get(models.Sop, row["symptom"])
            if obj is None:
                obj = models.Sop(**row)
                db.add(obj)
            else:
                for k, v in row.items():
                    if k != "symptom":
                        setattr(obj, k, v)
                obj.steps.clear()
            obj.steps = [models.SopStep(**s) for s in steps]
            stats["sops"] += 1
        db.flush()

        audit(db, "import", "atlas", "-", f"mode={mode} " + json.dumps(stats))
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        # 转成 400 并带上原因：调用方要知道是哪条数据有问题，
        # 而不是只看到 "Internal Server Error"
        raise HTTPException(400, f"导入失败，已整体回滚，数据未改动：{exc}") from exc
    return stats


# ------------------------------------------------------------------ 统计
def counts(db: Session) -> dict[str, int]:
    return {
        "layers": db.scalar(select(func.count()).select_from(models.Layer)) or 0,
        "groups": db.scalar(select(func.count()).select_from(models.Group)) or 0,
        "nodes": db.scalar(select(func.count()).select_from(models.Node)) or 0,
        "fields": db.scalar(select(func.count()).select_from(models.NodeField)) or 0,
        "edges": db.scalar(select(func.count()).select_from(models.Edge)) or 0,
        "notes": db.scalar(select(func.count()).select_from(models.Note)) or 0,
        "sops": db.scalar(select(func.count()).select_from(models.Sop)) or 0,
        "sop_steps": db.scalar(select(func.count()).select_from(models.SopStep)) or 0,
        "yamls": db.scalar(select(func.count()).select_from(models.YamlSnippet)) or 0,
        "audit": db.scalar(select(func.count()).select_from(models.AuditLog)) or 0,
    }
