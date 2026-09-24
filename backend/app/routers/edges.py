"""组件关系（连线）增删改查。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..db import get_db

router = APIRouter(prefix="/edges", tags=["关系"])


@router.get("", response_model=list[schemas.EdgeOut], summary="关系列表")
def list_edges(db: Session = Depends(get_db)):
    return crud.list_edges(db)


@router.post("", response_model=schemas.EdgeOut, status_code=201, summary="新建关系")
def create_edge(payload: schemas.EdgeIn, db: Session = Depends(get_db)):
    return crud.create_edge(db, payload.model_dump())


@router.get("/{edge_id}", response_model=schemas.EdgeOut, summary="关系详情")
def get_edge(edge_id: str, db: Session = Depends(get_db)):
    return crud.get_edge(db, edge_id)


@router.patch("/{edge_id}", response_model=schemas.EdgeOut, summary="修改关系")
def update_edge(edge_id: str, payload: schemas.EdgePatch, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise ValueError("没有需要更新的字段")
    return crud.update_edge(db, edge_id, data)


@router.delete("/{edge_id}", summary="删除关系")
def delete_edge(edge_id: str, db: Session = Depends(get_db)):
    return crud.delete_edge(db, edge_id)
