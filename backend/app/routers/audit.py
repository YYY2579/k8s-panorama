"""审计日志：所有写操作都会留一条，可用来验证"操作是否真的生效"。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..db import get_db

router = APIRouter(prefix="/audit", tags=["审计"])


@router.get("", response_model=list[schemas.AuditOut], summary="审计日志（倒序）")
def list_audit(
    limit: int = Query(50, ge=1, le=500),
    entity: str | None = Query(None, description="按实体过滤：node/edge/group/note/sop/yaml/layer/atlas/user"),
    actor: str | None = Query(None, description="按操作者过滤，如 admin"),
    db: Session = Depends(get_db),
):
    return crud.list_audit(db, limit, entity, actor)
