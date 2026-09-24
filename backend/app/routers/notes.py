"""知识条目 CRUD + 状态流转。

状态流转：draft --publish--> review --approve--> published
          任意状态 --archive--> archived --restore--> draft
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..db import get_db

router = APIRouter(prefix="/notes", tags=["知识条目"])


@router.get("", response_model=list[schemas.NoteOut], summary="知识条目列表")
def list_notes(status: str | None = None, node_id: str | None = None, db: Session = Depends(get_db)):
    return crud.list_notes(db, status, node_id)


@router.post("", response_model=schemas.NoteOut, status_code=201, summary="新建知识条目")
def create_note(payload: schemas.NoteIn, db: Session = Depends(get_db)):
    return crud.create_note(db, payload.model_dump())


@router.get("/{slug}", response_model=schemas.NoteOut, summary="知识条目详情")
def get_note(slug: str, db: Session = Depends(get_db)):
    return crud.get_note(db, slug)


@router.patch("/{slug}", response_model=schemas.NoteOut, summary="修改知识条目")
def update_note(slug: str, payload: schemas.NotePatch, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise ValueError("没有需要更新的字段")
    return crud.update_note(db, slug, data)


@router.delete("/{slug}", summary="删除知识条目")
def delete_note(slug: str, db: Session = Depends(get_db)):
    return crud.delete_note(db, slug)


@router.post("/{slug}/transition", response_model=schemas.NoteOut, summary="状态流转")
def transition(slug: str, payload: schemas.TransitionIn, db: Session = Depends(get_db)):
    return crud.transition_note(db, slug, payload.action, payload.comment)
