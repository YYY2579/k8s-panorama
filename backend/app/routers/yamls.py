"""YAML 实验室片段 CRUD。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..db import get_db
from ..deps import require_admin
from ..models import User
from ..deps import require_admin

router = APIRouter(prefix="/yamls", tags=["YAML片段"])


@router.get("", response_model=list[schemas.YamlOut], summary="YAML 列表")
def list_yamls(node_id: str | None = None, db: Session = Depends(get_db)):
    return crud.list_yamls(db, node_id)


@router.post("", response_model=schemas.YamlOut, status_code=201, summary="新建 YAML")
def create_yaml(payload: schemas.YamlIn, db: Session = Depends(get_db),
    admin: User = Depends(require_admin),):
    crud.set_actor(admin.username)
    return crud.create_yaml(db, payload.model_dump())


@router.get("/{yaml_id}", response_model=schemas.YamlOut, summary="YAML 详情")
def get_yaml(yaml_id: int, db: Session = Depends(get_db)):
    return crud.get_yaml(db, yaml_id)


@router.patch("/{yaml_id}", response_model=schemas.YamlOut, summary="修改 YAML")
def update_yaml(yaml_id: int, payload: schemas.YamlPatch, db: Session = Depends(get_db),
    admin: User = Depends(require_admin),):
    crud.set_actor(admin.username)
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise ValueError("没有需要更新的字段")
    return crud.update_yaml(db, yaml_id, data)


@router.delete("/{yaml_id}", summary="删除 YAML")
def delete_yaml(yaml_id: int, db: Session = Depends(get_db),
    admin: User = Depends(require_admin),):
    crud.set_actor(admin.username)
    return crud.delete_yaml(db, yaml_id)
