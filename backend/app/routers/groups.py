"""分组容器增删改查。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..db import get_db
from ..deps import require_admin
from ..models import User
from ..deps import require_admin

router = APIRouter(prefix="/groups", tags=["分组"])


@router.get("", response_model=list[schemas.GroupOut], summary="分组列表")
def list_groups(db: Session = Depends(get_db)):
    return crud.list_groups(db)


@router.post("", response_model=schemas.GroupOut, status_code=201, summary="新建分组")
def create_group(payload: schemas.GroupIn, db: Session = Depends(get_db),
    admin: User = Depends(require_admin),):
    crud.set_actor(admin.username)
    return crud.create_group(db, payload.model_dump())


@router.get("/{group_id}", response_model=schemas.GroupOut, summary="分组详情")
def get_group(group_id: str, db: Session = Depends(get_db)):
    return crud.get_group(db, group_id)


@router.patch("/{group_id}", response_model=schemas.GroupOut, summary="修改分组")
def update_group(group_id: str, payload: schemas.GroupPatch, db: Session = Depends(get_db),
    admin: User = Depends(require_admin),):
    crud.set_actor(admin.username)
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise ValueError("没有需要更新的字段")
    return crud.update_group(db, group_id, data)


@router.delete("/{group_id}", summary="删除分组")
def delete_group(
    group_id: str,
    force: bool = False,
    move_to: str | None = Query(None, description="force 时组件搬到哪个分组，不传则用排序第一个的其它分组"),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    crud.set_actor(admin.username)
    return crud.delete_group(db, group_id, force, move_to)
