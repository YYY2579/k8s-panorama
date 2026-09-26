"""图层 / 分类。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..db import get_db
from ..deps import require_admin
from ..models import User
from ..deps import require_admin

router = APIRouter(prefix="/layers", tags=["图层"])


@router.get("", response_model=list[schemas.LayerOut], summary="图层列表")
def list_layers(db: Session = Depends(get_db)):
    return crud.list_layers(db)


@router.patch("/{layer_id}", response_model=schemas.LayerOut, summary="修改图层（颜色、显隐、排序）")
def patch_layer(layer_id: str, payload: schemas.LayerPatch, db: Session = Depends(get_db),
    admin: User = Depends(require_admin),):
    crud.set_actor(admin.username)
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise ValueError("没有需要更新的字段")
    return crud.patch_layer(db, layer_id, data)
