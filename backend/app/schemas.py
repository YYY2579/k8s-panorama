"""Pydantic v2 请求 / 响应模型。

约定：
  *In     —— 新建入参
  *Patch  —— 局部更新入参（所有字段可选）
  *Out    —— 响应出参（from_attributes=True，可直接从 ORM 对象转换）
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------- 图层 ----------------
class LayerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    label: str
    color: str
    show_in_legend: bool
    show_in_filter: bool
    sort_order: int


class LayerPatch(BaseModel):
    label: str | None = None
    color: str | None = None
    show_in_legend: bool | None = None
    show_in_filter: bool | None = None
    sort_order: int | None = None


# ---------------- 分组 ----------------
class GroupIn(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    ordinal: str = Field(default="", max_length=4)
    title: str = Field(min_length=1, max_length=120)
    subtitle: str = Field(default="", max_length=160)
    x: int = 20
    y: int = 20
    w: int = 800
    h: int = 170
    sort_order: int = 0


class GroupPatch(BaseModel):
    ordinal: str | None = None
    title: str | None = Field(default=None, max_length=120)
    subtitle: str | None = None
    x: int | None = None
    y: int | None = None
    w: int | None = None
    h: int | None = None
    sort_order: int | None = None


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    ordinal: str
    title: str
    subtitle: str
    x: int
    y: int
    w: int
    h: int
    sort_order: int


# ---------------- 组件 ----------------
class NodeFieldIn(BaseModel):
    label: str = Field(default="", max_length=60)
    value: str = Field(default="", max_length=300)
    sort_order: int = 0


class NodeFieldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    node_id: str
    label: str
    value: str
    sort_order: int


class NodeIn(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    group_id: str
    layer_id: str
    name: str = Field(min_length=1, max_length=80)
    kind: str = Field(default="", max_length=80)
    summary: str = ""
    cmd: str = Field(default="", max_length=300)
    x: int = 0
    y: int = 0
    fields: list[NodeFieldIn] = Field(default_factory=list)


class NodePatch(BaseModel):
    group_id: str | None = None
    layer_id: str | None = None
    name: str | None = Field(default=None, max_length=80)
    kind: str | None = None
    summary: str | None = None
    cmd: str | None = None
    x: int | None = None
    y: int | None = None
    fields: list[NodeFieldIn] | None = None  # 传 null 表示不改；传 [] 表示清空


class NodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    group_id: str
    layer_id: str
    name: str
    kind: str
    summary: str
    cmd: str
    x: int
    y: int
    created_at: datetime
    updated_at: datetime
    fields: list[NodeFieldOut] = Field(default_factory=list)


# ---------------- 关系 ----------------
class EdgeIn(BaseModel):
    id: str | None = None  # 不传则自动生成 "<from>-><to>"
    from_node: str
    to_node: str
    label: str = Field(default="", max_length=60)
    layer_id: str | None = None
    sort_order: int = 0


class EdgePatch(BaseModel):
    label: str | None = None
    layer_id: str | None = None
    sort_order: int | None = None


class EdgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    from_node: str
    to_node: str
    label: str
    layer_id: str | None
    sort_order: int


# ---------------- 知识条目 ----------------
class NoteIn(BaseModel):
    slug: str = Field(min_length=1, max_length=120)
    node_id: str | None = None
    title: str = Field(min_length=1, max_length=200)
    markdown: str = ""
    status: Literal["draft", "review", "published", "archived"] = "draft"


class NotePatch(BaseModel):
    node_id: str | None = None
    title: str | None = None
    markdown: str | None = None
    status: Literal["draft", "review", "published", "archived"] | None = None


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    node_id: str | None
    title: str
    markdown: str
    status: str
    created_at: datetime
    updated_at: datetime


class TransitionIn(BaseModel):
    """状态流转动作。"""

    action: Literal["publish", "approve", "archive", "restore"]
    comment: str = ""


# ---------------- 排障 SOP ----------------
class SopStepIn(BaseModel):
    step_no: int
    action: str = ""
    expect: str = ""
    command: str = Field(default="", max_length=300)


class SopStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sop_id: str
    step_no: int
    action: str
    expect: str
    command: str


class SopIn(BaseModel):
    symptom: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    status: Literal["draft", "review", "published", "archived"] = "draft"
    steps: list[SopStepIn] = Field(default_factory=list)


class SopPatch(BaseModel):
    title: str | None = None
    status: Literal["draft", "review", "published", "archived"] | None = None
    steps: list[SopStepIn] | None = None


class SopOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symptom: str
    title: str
    status: str
    created_at: datetime
    updated_at: datetime
    steps: list[SopStepOut] = Field(default_factory=list)


# ---------------- YAML 片段 ----------------
class YamlIn(BaseModel):
    node_id: str | None = None
    title: str = Field(min_length=1, max_length=200)
    yaml: str = ""


class YamlPatch(BaseModel):
    node_id: str | None = None
    title: str | None = None
    yaml: str | None = None


class YamlOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    node_id: str | None
    title: str
    yaml: str


# ---------------- 审计 ----------------
class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    entity: str
    entity_id: str
    detail: str
    actor: str
    created_at: datetime


# ---------------- 认证 ----------------
class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None


class UserIn(BaseModel):
    """新建用户（仅 admin 可调）。"""

    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=200)
    role: Literal["admin", "viewer"] = "viewer"


class UserPatch(BaseModel):
    password: str | None = Field(default=None, min_length=8, max_length=200)
    role: Literal["admin", "viewer"] | None = None
    is_active: bool | None = None


class PasswordChangeIn(BaseModel):
    old_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


# ---------------- 导入 ----------------
class ImportPayload(BaseModel):
    """导入接口的结构校验。

    各列表字段必须是数组（元素是 dict，字段级过滤由 crud._coerce_row 负责）；
    顶层允许额外字段，便于向后兼容导出格式的增补。
    """

    model_config = ConfigDict(extra="allow")

    version: int = 1
    layers: list[dict] = Field(default_factory=list)
    groups: list[dict] = Field(default_factory=list)
    nodes: list[dict] = Field(default_factory=list)
    edges: list[dict] = Field(default_factory=list)
    notes: list[dict] = Field(default_factory=list)
    sops: list[dict] = Field(default_factory=list)
    yamls: list[dict] = Field(default_factory=list)


# ---------------- 聚合 / 搜索 ----------------
class GraphOut(BaseModel):
    """前端首屏一次拿全。"""

    layers: list[LayerOut]
    groups: list[GroupOut]
    nodes: list[NodeOut]
    edges: list[EdgeOut]
    generated_at: datetime


class SearchItem(BaseModel):
    type: str  # node | note | sop
    id: str
    title: str
    subtitle: str = ""
    node_id: str | None = None


class SearchOut(BaseModel):
    query: str
    total: int
    items: list[SearchItem]


class HealthOut(BaseModel):
    status: str
    database: str
    counts: dict[str, int]
