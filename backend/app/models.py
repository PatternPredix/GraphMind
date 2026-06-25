"""SQLAlchemy ORM models.

All annotation positions are stored as character offsets into Document.text
(the single source of truth), which keeps spans stable regardless of how the
frontend renders the text.
"""
import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow():
    return datetime.datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    guideline: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # Minimum human annotations per type before Auto-Annotate unlocks.
    auto_annotate_threshold: Mapped[int] = mapped_column(Integer, default=20)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)

    entity_types: Mapped[list["EntityType"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    relation_types: Mapped[list["RelationType"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    members: Mapped[list["ProjectMember"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(50), default="annotator")  # admin | annotator

    project: Mapped["Project"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship()


class EntityType(Base):
    __tablename__ = "entity_types"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    color: Mapped[str] = mapped_column(String(20), default="#fbbf24")
    hotkey: Mapped[str] = mapped_column(String(1), default="")

    project: Mapped["Project"] = relationship(back_populates="entity_types")


class RelationType(Base):
    __tablename__ = "relation_types"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    color: Mapped[str] = mapped_column(String(20), default="#60a5fa")

    project: Mapped["Project"] = relationship(back_populates="relation_types")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_project_order", "project_id", "order_index"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    # Set when a human marks the document's annotations as complete/reviewed.
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    confirmed_by: Mapped[int] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)

    spans: Mapped[list["Span"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    relations: Mapped[list["Relation"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Span(Base):
    """An entity annotation: [start_offset, end_offset) character span."""

    __tablename__ = "spans"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    entity_type_id: Mapped[int] = mapped_column(ForeignKey("entity_types.id", ondelete="CASCADE"))
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(10), default="human")  # human | model
    confidence: Mapped[float] = mapped_column(Float, nullable=True)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=True)  # model spans start False
    created_by: Mapped[int] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)

    document: Mapped["Document"] = relationship(back_populates="spans")
    entity_type: Mapped["EntityType"] = relationship()


class Relation(Base):
    """A directed relation between two spans in the same document."""

    __tablename__ = "relations"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    relation_type_id: Mapped[int] = mapped_column(
        ForeignKey("relation_types.id", ondelete="CASCADE")
    )
    from_span_id: Mapped[int] = mapped_column(ForeignKey("spans.id", ondelete="CASCADE"))
    to_span_id: Mapped[int] = mapped_column(ForeignKey("spans.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(10), default="human")
    confidence: Mapped[float] = mapped_column(Float, nullable=True)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)

    document: Mapped["Document"] = relationship(back_populates="relations")
    relation_type: Mapped["RelationType"] = relationship()
    from_span: Mapped["Span"] = relationship(foreign_keys=[from_span_id])
    to_span: Mapped["Span"] = relationship(foreign_keys=[to_span_id])


class EntityKeywordRule(Base):
    """A gazetteer rule: every occurrence of `keyword` is tagged as an entity.

    Applying the rule scans all documents and creates spans (source="rule",
    reviewed=True) for each match that does not already exist.
    """

    __tablename__ = "entity_keyword_rules"
    __table_args__ = (
        UniqueConstraint("project_id", "entity_type_id", "keyword", "case_sensitive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    entity_type_id: Mapped[int] = mapped_column(
        ForeignKey("entity_types.id", ondelete="CASCADE")
    )
    keyword: Mapped[str] = mapped_column(String(255))
    case_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    whole_word: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)

    entity_type: Mapped["EntityType"] = relationship()


class RelationRule(Base):
    """An embedding-similarity rule for relation extraction.

    For each ordered pair of entities matching (head_entity_type,
    tail_entity_type) within `max_distance` characters, the text spanning the
    pair is embedded and compared (cosine) against this rule's `description`
    embedding. Pairs scoring >= `threshold` get a relation of `relation_type`
    (source="rule", reviewed=False, confidence=similarity).

    The description embedding is computed once, at rule creation, and stored
    here; applying the rule never re-embeds the description.
    """

    __tablename__ = "relation_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    relation_type_id: Mapped[int] = mapped_column(
        ForeignKey("relation_types.id", ondelete="CASCADE")
    )
    head_entity_type_id: Mapped[int] = mapped_column(
        ForeignKey("entity_types.id", ondelete="CASCADE")
    )
    tail_entity_type_id: Mapped[int] = mapped_column(
        ForeignKey("entity_types.id", ondelete="CASCADE")
    )
    description: Mapped[str] = mapped_column(Text)
    # Cached embedding of `description` (list[float]) and the model that made it.
    embedding: Mapped[list] = mapped_column(JSON, default=list)
    embedding_model: Mapped[str] = mapped_column(String(255), default="")
    threshold: Mapped[float] = mapped_column(Float, default=0.55)
    max_distance: Mapped[int] = mapped_column(Integer, default=200)
    created_by: Mapped[int] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)

    relation_type: Mapped["RelationType"] = relationship()
    head_entity_type: Mapped["EntityType"] = relationship(
        foreign_keys=[head_entity_type_id]
    )
    tail_entity_type: Mapped["EntityType"] = relationship(
        foreign_keys=[tail_entity_type_id]
    )


class TrainingJob(Base):
    """A background auto-annotation job: train, then annotate remaining docs.

    Also used for rule-application jobs (task="ner_rules" / "re_rules").
    """

    __tablename__ = "training_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    task: Mapped[str] = mapped_column(String(10))  # ner | re
    status: Mapped[str] = mapped_column(String(20), default="queued")
    # queued -> training -> annotating -> completed | failed
    progress: Mapped[float] = mapped_column(Float, default=0.0)  # 0..1
    message: Mapped[str] = mapped_column(Text, default="")
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    annotated_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=True)
