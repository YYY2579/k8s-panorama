"""ORM 模型：10 张表。

表关系
  layer 1──n node 1──n node_field
  group 1──n node
  node  1──n edge（from_node / to_node 两侧都指向 node）
  node  1──n note, 1──n yaml_snippet
  sop   1──n sop_step
  audit_log 独立（记录所有写操作）
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _now():
    """统一返回 naive UTC 时间。

    SQLite 的 DateTime 列不保存时区信息：写 aware 读回来是 naive，
    两种表示混用会在比较时抛 TypeError。这里在源头统一成 naive UTC，
    语义（UTC）不变，读写一致。
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Layer(Base):
    """分类 / 图层（8 项，同时驱动画布图例与左栏过滤）。"""

    __tablename__ = "layer"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    label: Mapped[str] = mapped_column(String(40), nullable=False)
    color: Mapped[str] = mapped_column(String(9), nullable=False, default="#4FA3F7")
    show_in_legend: Mapped[bool] = mapped_column(default=True)
    show_in_filter: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    nodes: Mapped[list["Node"]] = relationship(back_populates="layer")


class Group(Base):
    """画布上的分组容器（编号①~⑨，参考图中跳过⑥，此处忠实保留）。"""

    __tablename__ = "atlas_group"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    ordinal: Mapped[str] = mapped_column(String(4), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    subtitle: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    x: Mapped[int] = mapped_column(Integer, default=20)
    y: Mapped[int] = mapped_column(Integer, default=20)
    w: Mapped[int] = mapped_column(Integer, default=800)
    h: Mapped[int] = mapped_column(Integer, default=170)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    nodes: Mapped[list["Node"]] = relationship(back_populates="group")


class Node(Base):
    """组件节点（卡片）。"""

    __tablename__ = "node"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    group_id: Mapped[str] = mapped_column(ForeignKey("atlas_group.id"), nullable=False)
    layer_id: Mapped[str] = mapped_column(ForeignKey("layer.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cmd: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    x: Mapped[int] = mapped_column(Integer, default=0)
    y: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    group: Mapped["Group"] = relationship(back_populates="nodes")
    layer: Mapped["Layer"] = relationship(back_populates="nodes")
    fields: Mapped[list["NodeField"]] = relationship(
        back_populates="node", cascade="all, delete-orphan", order_by="NodeField.sort_order"
    )


class NodeField(Base):
    """组件卡片第三行的关键字段（label：value）。"""

    __tablename__ = "node_field"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(ForeignKey("node.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    value: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    node: Mapped["Node"] = relationship(back_populates="fields")


class Edge(Base):
    """组件之间的有向关系（连线）。"""

    __tablename__ = "edge"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    from_node: Mapped[str] = mapped_column(ForeignKey("node.id", ondelete="CASCADE"), nullable=False)
    to_node: Mapped[str] = mapped_column(ForeignKey("node.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    layer_id: Mapped[str] = mapped_column(ForeignKey("layer.id"), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Note(Base):
    """知识条目（含状态流转 draft → review → published，可 archived）。"""

    __tablename__ = "note"

    slug: Mapped[str] = mapped_column(String(120), primary_key=True)
    node_id: Mapped[str] = mapped_column(ForeignKey("node.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Sop(Base):
    """排障 SOP（状态流转同 Note）。"""

    __tablename__ = "sop"

    symptom: Mapped[str] = mapped_column(String(120), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    steps: Mapped[list["SopStep"]] = relationship(
        back_populates="sop", cascade="all, delete-orphan", order_by="SopStep.step_no"
    )


class SopStep(Base):
    """SOP 的一个步骤：做什么、期望看到什么、可选命令。"""

    __tablename__ = "sop_step"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sop_id: Mapped[str] = mapped_column(ForeignKey("sop.symptom", ondelete="CASCADE"), nullable=False)
    step_no: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expect: Mapped[str] = mapped_column(Text, nullable=False, default="")
    command: Mapped[str] = mapped_column(String(300), nullable=False, default="")

    sop: Mapped["Sop"] = relationship(back_populates="steps")


class YamlSnippet(Base):
    """YAML 实验室的片段。"""

    __tablename__ = "yaml_snippet"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(ForeignKey("node.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    yaml: Mapped[str] = mapped_column(Text, nullable=False, default="")


class AuditLog(Base):
    """审计日志：每次写操作（create/update/delete/transition/import）都会写一条。"""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    entity: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
