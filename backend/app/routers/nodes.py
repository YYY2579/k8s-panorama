"""组件（节点）增删改查。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..db import get_db
from ..deps import require_admin
from ..models import User
from ..deps import require_admin

router = APIRouter(prefix="/nodes", tags=["组件"])


@router.get("", response_model=list[schemas.NodeOut], summary="组件列表")
def list_nodes(
    group_id: str | None = None,
    layer_id: str | None = None,
    db: Session = Depends(get_db),
):
    return crud.list_nodes(db, group_id, layer_id)


@router.post("", response_model=schemas.NodeOut, status_code=201, summary="新建组件")
def create_node(payload: schemas.NodeIn, db: Session = Depends(get_db),
    admin: User = Depends(require_admin),):
    crud.set_actor(admin.username)
    return crud.create_node(db, payload.model_dump())


@router.get("/{node_id}", response_model=schemas.NodeOut, summary="组件详情")
def get_node(node_id: str, db: Session = Depends(get_db)):
    return crud.get_node(db, node_id)


@router.patch("/{node_id}", response_model=schemas.NodeOut, summary="修改组件")
def update_node(node_id: str, payload: schemas.NodePatch, db: Session = Depends(get_db),
    admin: User = Depends(require_admin),):
    crud.set_actor(admin.username)
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise ValueError("没有需要更新的字段")
    return crud.update_node(db, node_id, data)


@router.delete("/{node_id}", summary="删除组件")
def delete_node(node_id: str, db: Session = Depends(get_db),
    admin: User = Depends(require_admin),):
    crud.set_actor(admin.username)
    return crud.delete_node(db, node_id)
