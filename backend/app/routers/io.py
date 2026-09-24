"""导出 / 导入：真实读写数据库，可用来做备份与迁移。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import crud
from ..db import get_db

router = APIRouter(prefix="/io", tags=["导入导出"])


@router.get("/export", summary="导出全库为 JSON")
def export(db: Session = Depends(get_db)):
    return crud.export_all(db)


@router.post("/import", summary="导入 JSON 到库（replace 覆盖 / merge 合并）")
def import_data(
    payload: dict,
    mode: str = Query("merge", pattern="^(merge|replace)$"),
    db: Session = Depends(get_db),
):
    return {"mode": mode, "imported": crud.import_all(db, payload, mode), "counts": crud.counts(db)}
