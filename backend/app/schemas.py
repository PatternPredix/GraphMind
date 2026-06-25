"""Pydantic request/response schemas."""
import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------- Auth / users ----------

class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=150)
    email: str
    password: str = Field(min_length=6)
    is_admin: bool = False


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    email: str
    is_admin: bool


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=1, max_length=255)


# ---------- Projects ----------

class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    guideline: str = ""
    auto_annotate_threshold: Optional[int] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    guideline: Optional[str] = None
    auto_annotate_threshold: Optional[int] = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str
    guideline: str
    owner_id: int
    auto_annotate_threshold: int
    created_at: datetime.datetime


class ProjectStats(BaseModel):
    total_documents: int
    confirmed_documents: int
    total_spans: int
    total_relations: int
    unreviewed_model_spans: int
    unreviewed_model_relations: int


class MemberAdd(BaseModel):
    username: str
    role: str = "annotator"


class MemberOut(BaseModel):
    id: int
    user_id: int
    username: str
    role: str


# ---------- Labels ----------

class EntityTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: str = "#fbbf24"
    hotkey: str = ""


class EntityTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    color: str
    hotkey: str


class RelationTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: str = "#60a5fa"


class RelationTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    color: str


# ---------- Documents ----------

class DocumentCreate(BaseModel):
    text: str
    meta: Dict[str, Any] = {}


class DocumentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    snippet: str
    is_confirmed: bool
    span_count: int
    relation_count: int
    has_unreviewed: bool


class DocumentPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[DocumentSummary]


class SpanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    entity_type_id: int
    start_offset: int
    end_offset: int
    source: str
    confidence: Optional[float]
    reviewed: bool


class RelationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    relation_type_id: int
    from_span_id: int
    to_span_id: int
    source: str
    confidence: Optional[float]
    reviewed: bool


class DocumentDetail(BaseModel):
    id: int
    text: str
    meta: Dict[str, Any]
    is_confirmed: bool
    spans: List[SpanOut]
    relations: List[RelationOut]
    # ids of previous/next document in project order, for fast navigation
    prev_id: Optional[int]
    next_id: Optional[int]
    position: int  # 1-based position within the current filter
    total: int


class BulkDelete(BaseModel):
    document_ids: List[int]


# ---------- Annotations ----------

class SpanCreate(BaseModel):
    entity_type_id: int
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)


class SpanUpdate(BaseModel):
    entity_type_id: Optional[int] = None
    reviewed: Optional[bool] = None


class RelationCreate(BaseModel):
    relation_type_id: int
    from_span_id: int
    to_span_id: int


class RelationUpdate(BaseModel):
    relation_type_id: Optional[int] = None
    reviewed: Optional[bool] = None


class ConfirmRequest(BaseModel):
    is_confirmed: bool


# ---------- Auto-annotation ----------

class TypeProgress(BaseModel):
    id: int
    name: str
    count: int
    threshold: int
    eligible: bool


class AutoAnnotateEligibility(BaseModel):
    task: str
    eligible: bool
    threshold: int
    types: List[TypeProgress]
    reason: str = ""


class AutoAnnotateRequest(BaseModel):
    task: str  # "ner" | "re"


class TrainingJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    task: str
    status: str
    progress: float
    message: str
    metrics: Dict[str, Any]
    annotated_count: int
    created_at: datetime.datetime
    finished_at: Optional[datetime.datetime]


# ---------- Rules ----------

class KeywordRuleCreate(BaseModel):
    entity_type_id: int
    keyword: str = Field(min_length=1, max_length=255)
    case_sensitive: bool = False
    whole_word: bool = True


class KeywordRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    entity_type_id: int
    keyword: str
    case_sensitive: bool
    whole_word: bool


class RelationRuleCreate(BaseModel):
    relation_type_id: int
    head_entity_type_id: int
    tail_entity_type_id: int
    description: str = Field(min_length=1)
    threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max_distance: int = Field(default=200, ge=1, le=2000)


class RelationRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    relation_type_id: int
    head_entity_type_id: int
    tail_entity_type_id: int
    description: str
    embedding_model: str
    threshold: float
    max_distance: int
    has_embedding: bool


# ---------- Import / export ----------

class ImportResult(BaseModel):
    imported_documents: int
    imported_spans: int
    imported_relations: int
    created_entity_types: List[str]
    created_relation_types: List[str]
    warnings: List[str]
