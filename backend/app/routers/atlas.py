"""图谱聚合、检索、视图、健康检查。"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..db import get_db
from ..models import Group

router = APIRouter(prefix="/atlas", tags=["图谱"])


@router.get("/health", response_model=schemas.HealthOut, summary="健康检查与库内计数")
def health(db: Session = Depends(get_db)):
    return {
        "status": "ok",
        "database": "sqlite",
        "counts": crud.counts(db),
    }


@router.get("/graph", response_model=schemas.GraphOut, summary="一次拿全部分组/组件/关系/图层")
def graph(db: Session = Depends(get_db)):
    return {
        "layers": crud.list_layers(db),
        "groups": crud.list_groups(db),
        "nodes": crud.list_nodes(db),
        "edges": crud.list_edges(db),
        "generated_at": datetime.now(timezone.utc),
    }


@router.get("/search", response_model=schemas.SearchOut, summary="跨组件/知识/SOP 检索")
def search(
    q: str = Query(..., min_length=1, description="关键词，支持组件名、类型、命令、知识正文"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    items = crud.search(db, q, limit)
    return {"query": q, "total": len(items), "items": items}


@router.get("/views", summary="左侧「视图」定义（聚焦哪些分组）")
def views(db: Session = Depends(get_db)):
    groups = list(db.scalars(__import__("sqlalchemy").select(Group).order_by(Group.sort_order)).all())
    by_id = {g.id: g.title for g in groups}

    def pick(ids):
        return [{"id": i, "label": by_id.get(i, i)} for i in ids if i in by_id]

    return [
        {"id": "all", "label": "全景", "target_groups": [g.id for g in groups]},
        {"id": "control", "label": "控制面", "target_groups": ["g1"]},
        {"id": "node", "label": "节点", "target_groups": ["g2"]},
        {"id": "network", "label": "网络", "target_groups": ["g3", "g4"]},
        {"id": "workload", "label": "工作负载", "target_groups": ["g5"]},
        {"id": "security", "label": "安全存储", "target_groups": ["g7", "g6"]},
        {"id": "observability", "label": "可观测", "target_groups": ["g8"]},
    ]
