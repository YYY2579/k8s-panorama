"""导出 / 导入：真实读写数据库，可用来做备份与迁移。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import crud
from ..db import get_db
from ..deps import require_admin
from ..models import User
from ..deps import require_admin
from ..schemas import ImportPayload

router = APIRouter(prefix="/io", tags=["导入导出"])


@router.get("/export", summary="导出全库为 JSON")
def export(db: Session = Depends(get_db)):
    return crud.export_all(db)


@router.post("/import", summary="导入 JSON 到库（replace 覆盖 / merge 合并）")
def import_data(
    payload: ImportPayload,
    mode: str = Query("merge", pattern="^(merge|replace)$"),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """结构不合法的 JSON 会被 Pydantic 拦成 422，不会进入写库环节。"""
    crud.set_actor(admin.username)
    return {
        "mode": mode,
        "imported": crud.import_all(db, payload.model_dump(), mode),
        "counts": crud.counts(db),
    }
