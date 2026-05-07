"""Pydantic data models for KB-Curator (domain schemas)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


# ============================================================
# Enumerations
# ============================================================

class ChangeType(str, Enum):
    NEW_INFO = "new_info"
    POLICY_CHANGE = "policy_change"
    CONTRADICTION = "contradiction"
    CORRECTION = "correction"
    REDUNDANT = "redundant"

class ConflictType(str, Enum):
    SEMANTIC = "semantic"
    STRUCTURAL = "structural"
    TEMPORAL = "temporal"

class DecisionType(str, Enum):
    ACCEPT_NEW = "accept_new"
    KEEP_OLD = "keep_old"
    MERGE = "merge"
    IGNORE = "ignore"
    DELETE = "delete"
    ARCHIVE = "archive"

class UpdateStrategy(str, Enum):
    APPEND = "append"
    CREATE = "create"
    REPLACE = "replace"
    DELETE = "delete"
    ARCHIVE = "archive"

class EntryStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DEPRECATED = "deprecated"

class ReviewTaskType(str, Enum):
    CONFLICT_RESOLUTION = "conflict_resolution"
    QUALITY_ACTION = "quality_action"
    DEPRECATION = "deprecation"

class ReviewTaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    EXPIRED = "expired"

class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

class QualityIssueType(str, Enum):
    LOW_HIT_RATE = "low_hit_rate"
    HIGH_NEGATIVE_FEEDBACK = "high_negative_feedback"
    EXPIRED = "expired"
    ORPHAN_ENTITY = "orphan_entity"
    METADATA_INCONSISTENCY = "metadata_inconsistency"


# ============================================================
# Data Source
# ============================================================

class DataSourceCreate(BaseModel):
    """Request body for creating a data source."""
    kb_id: str
    name: str
    source_type: Literal["wiki", "confluence", "jira", "file", "conversation_log"]
    connection_config: dict = {}
    poll_interval_minutes: int = 60
    enabled: bool = True

class DataSourceRead(BaseModel):
    """Response model for a data source."""
    id: str
    kb_id: str
    name: str
    source_type: str
    connection_config: dict = {}
    poll_interval_minutes: int = 60
    last_polled_at: datetime | None = None
    last_fingerprint: str | None = None
    enabled: bool = True
    created_at: datetime


# ============================================================
# Change Event
# ============================================================

class ChangeEventCreate(BaseModel):
    """Internal model for creating a change event."""
    kb_id: str
    source_id: str
    change_type: ChangeType
    title: str
    content_before: str | None = None
    content_after: str | None = None
    fingerprint_before: str | None = None
    fingerprint_after: str | None = None
    metadata: dict = {}

class ChangeEventRead(BaseModel):
    """Response model for a change event."""
    id: str
    kb_id: str
    source_id: str
    change_type: ChangeType
    title: str
    content_before: str | None = None
    content_after: str | None = None
    detected_at: datetime


# ============================================================
# Knowledge Entry
# ============================================================

class KnowledgeEntryCreate(BaseModel):
    """Request body for manually creating a knowledge entry."""
    kb_id: str
    title: str
    content: str
    source_id: str
    source_url: str | None = None
    tags: list[str] = []
    expires_at: datetime | None = None
    metadata: dict = {}

class KnowledgeEntryUpdate(BaseModel):
    """Request body for updating a knowledge entry."""
    title: str | None = None
    content: str | None = None
    tags: list[str] | None = None
    status: EntryStatus | None = None
    expires_at: datetime | None = None
    metadata: dict | None = None

class KnowledgeEntryRead(BaseModel):
    """Response model for a knowledge entry."""
    id: str
    kb_id: str
    title: str
    content: str
    source_id: str
    source_url: str | None = None
    version: int
    status: EntryStatus
    tags: list[str] = []
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
    metadata: dict = {}


# ============================================================
# Text Chunk
# ============================================================

class TextChunk(BaseModel):
    """A text chunk with optional embedding for vector storage."""
    id: str = Field(default_factory=lambda: uuid4().hex)
    kb_id: str
    entry_id: str
    content: str
    chunk_index: int
    embedding: list[float] | None = None
    embedding_id: str | None = None
    entity_ids: list[str] = []
    metadata: dict = {}


# ============================================================
# Knowledge Graph
# ============================================================

class KGEntityCreate(BaseModel):
    """Request body for creating/updating a KG entity."""
    id: str = ""
    kb_id: str
    name: str
    entity_type: str
    properties: dict = {}
    confidence: float = 1.0

class KGEntityRead(BaseModel):
    """Response model for a KG entity."""
    id: str
    kb_id: str
    name: str
    entity_type: str
    properties: dict = {}
    entry_ids: list[str] = []
    confidence: float = 1.0
    created_at: datetime

class KGRelationCreate(BaseModel):
    """Request body for creating a KG relation."""
    kb_id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    properties: dict = {}
    confidence: float = 1.0

class KGRelationRead(BaseModel):
    """Response model for a KG relation."""
    id: str
    kb_id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    properties: dict = {}
    confidence: float = 1.0
    created_at: datetime


# ============================================================
# Conflict
# ============================================================

class ConflictRead(BaseModel):
    """Response model for a conflict."""
    id: str
    kb_id: str
    change_event_id: str
    conflict_type: ConflictType
    existing_entry_id: str | None = None
    existing_entity_id: str | None = None
    new_content: str
    existing_content: str
    summary: str
    severity: Severity = Severity.WARNING
    detected_at: datetime


# ============================================================
# Review & Decision
# ============================================================

class ReviewTaskRead(BaseModel):
    """Response model for a review task."""
    id: str
    kb_id: str
    conflict_id: str | None = None
    task_type: ReviewTaskType
    title: str
    description: str
    status: ReviewTaskStatus = ReviewTaskStatus.PENDING
    assigned_to: str | None = None
    auto_resolve_at: datetime | None = None
    created_at: datetime
    resolved_at: datetime | None = None

class DecisionRequest(BaseModel):
    """Request body for submitting a review decision."""
    decision_type: DecisionType
    rationale: str
    merge_content: str | None = None

class DecisionRead(BaseModel):
    """Response model for a decision."""
    id: str
    review_task_id: str
    decision_type: DecisionType
    rationale: str
    decided_by: str
    merge_content: str | None = None
    decided_at: datetime


# ============================================================
# Update Plan
# ============================================================

class UpdateOperation(BaseModel):
    """A single update operation in an update plan."""
    target: Literal["vector_store", "graph_store", "knowledge_entry"]
    strategy: UpdateStrategy
    entity_id: str | None = None
    entry_id: str | None = None
    data: dict = {}

class UpdatePlan(BaseModel):
    """A plan for updating the knowledge base."""
    id: str = Field(default_factory=lambda: uuid4().hex)
    kb_id: str
    operations: list[UpdateOperation]
    requires_human_approval: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================
# Quality
# ============================================================

class QualityIssue(BaseModel):
    """A single quality issue found during inspection."""
    entry_id: str
    issue_type: QualityIssueType
    severity: Severity
    detail: str
    suggestion: str

class QualityReportRead(BaseModel):
    """Response model for a quality report."""
    id: str
    kb_id: str
    inspection_type: Literal["full", "incremental", "targeted"]
    total_entries: int
    issues: list[QualityIssue]
    score: float
    inspected_at: datetime


# ============================================================
# Agent State (LangGraph)
# ============================================================

class AgentState(BaseModel):
    """LangGraph Agent state model."""
    change_event: ChangeEventCreate | None = None
    kb_id: str | None = None
    extracted_entities: list[KGEntityCreate] = []
    extracted_relations: list[KGRelationCreate] = []
    extracted_facts: list[dict] = []
    text_chunks: list[TextChunk] = []
    conflicts: list[ConflictRead] = []
    has_conflict: bool = False
    review_tasks: list[ReviewTaskRead] = []
    human_decisions: list[DecisionRead] = []
    update_plan: UpdatePlan | None = None
    execution_result: dict | None = None
    errors: list[str] = []
    metadata: dict = {}


# ============================================================
# Search
# ============================================================

class SearchRequest(BaseModel):
    """Request body for semantic search."""
    query: str
    top_k: int = 10
    filters: dict = {}

class SearchResult(BaseModel):
    """A single search result."""
    entry_id: str
    content: str
    score: float
    metadata: dict = {}


# ============================================================
# Execution Result
# ============================================================

class ExecutionResult(BaseModel):
    """Result of a pipeline execution."""
    success: bool
    status: str = "completed"
    thread_id: str | None = None
    operations_completed: int = 0
    errors: list[str] = []
    duration_ms: float = 0.0


# ============================================================
# LLM Judgments
# ============================================================

class ContradictionJudgment(BaseModel):
    """LLM judgment on whether two statements contradict."""
    is_contradiction: bool
    explanation: str
    severity: Severity = Severity.WARNING
