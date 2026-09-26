"""出厂概念图谱：直接由 seed 常量生成，不读库。

用途：前端「官方全景」数据源 —— 用户把自己的库改乱之后，仍有一份可对照的出厂状态。
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..seed import EDGES, GROUPS, LAYERS, NODES
from .. import schemas

router = APIRouter(prefix="/atlas", tags=["图谱"])


@router.get("/official", response_model=schemas.GraphOut, summary="出厂概念图谱（来自种子数据，不受编辑影响）")
def official(db: Session = Depends(get_db)):
    """与 /api/atlas/graph 结构一致，但内容取自 seed 常量。"""
    layer_rows = [schemas.LayerOut(id=r["id"], label=r["label"], color=r["color"],
                                  show_in_legend=True, show_in_filter=True, sort_order=i)
                  for i, r in enumerate(LAYERS)]
    group_rows = [schemas.GroupOut(sort_order=i, **r) for i, r in enumerate(GROUPS)]
    node_rows = []
    for r in NODES:
        fields = r.pop("fields", []) if isinstance(r, dict) else []
        row = {k: v for k, v in r.items() if k != "fields"}
        node_rows.append(schemas.NodeOut(
            **row,
            created_at=datetime(2026, 9, 25), updated_at=datetime(2026, 9, 25),
            fields=[schemas.NodeFieldOut(id=i + 1, node_id=row["id"], sort_order=i, **f)
                    for i, f in enumerate(fields)],
        ))
    edge_rows = [schemas.EdgeOut(**r) for r in EDGES]
    return {
        "layers": layer_rows,
        "groups": group_rows,
        "nodes": node_rows,
        "edges": edge_rows,
        "generated_at": datetime.now(timezone.utc),
    }
