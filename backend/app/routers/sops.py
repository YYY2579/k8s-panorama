"""排障 SOP CRUD + 状态流转。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..db import get_db

router = APIRouter(prefix="/sops", tags=["排障SOP"])


@router.get("", response_model=list[schemas.SopOut], summary="SOP 列表")
def list_sops(status: str | None = None, db: Session = Depends(get_db)):
    return crud.list_sops(db, status)


@router.post("", response_model=schemas.SopOut, status_code=201, summary="新建 SOP")
def create_sop(payload: schemas.SopIn, db: Session = Depends(get_db)):
    return crud.create_sop(db, payload.model_dump())


@router.get("/{symptom}", response_model=schemas.SopOut, summary="SOP 详情")
def get_sop(symptom: str, db: Session = Depends(get_db)):
    return crud.get_sop(db, symptom)


@router.patch("/{symptom}", response_model=schemas.SopOut, summary="修改 SOP")
def update_sop(symptom: str, payload: schemas.SopPatch, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise ValueError("没有需要更新的字段")
    return crud.update_sop(db, symptom, data)


@router.delete("/{symptom}", summary="删除 SOP")
def delete_sop(symptom: str, db: Session = Depends(get_db)):
    return crud.delete_sop(db, symptom)


@router.post("/{symptom}/transition", response_model=schemas.SopOut, summary="状态流转")
def transition(symptom: str, payload: schemas.TransitionIn, db: Session = Depends(get_db)):
    return crud.transition_sop(db, symptom, payload.action, payload.comment)
