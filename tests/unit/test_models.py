"""Unit tests for Pydantic data models."""

import pytest

from kb_curator.models.schemas import (
    ChangeEventCreate,
    ChangeType,
    ConflictType,
    DecisionRequest,
    DecisionType,
    KnowledgeEntryCreate,
    SearchRequest,
    Severity,
)


def test_change_event_create():
    """Test creating a ChangeEventCreate model."""
    event = ChangeEventCreate(
        kb_id="kb_001",
        source_id="src_001",
        change_type=ChangeType.POLICY_CHANGE,
        title="退款政策更新",
        content_after="本公司产品支持7天无理由退款。",
    )
    assert event.kb_id == "kb_001"
    assert event.change_type == ChangeType.POLICY_CHANGE


def test_knowledge_entry_create():
    """Test creating a KnowledgeEntryCreate model."""
    entry = KnowledgeEntryCreate(
        kb_id="kb_001",
        title="退款政策",
        content="本公司产品支持7天无理由退款。",
        source_id="src_001",
        tags=["policy", "refund"],
    )
    assert entry.tags == ["policy", "refund"]


def test_decision_request():
    """Test creating a DecisionRequest model."""
    req = DecisionRequest(
        decision_type=DecisionType.ACCEPT_NEW,
        rationale="新政策已生效",
    )
    assert req.decision_type == DecisionType.ACCEPT_NEW
    assert req.merge_content is None


def test_search_request():
    """Test creating a SearchRequest model."""
    req = SearchRequest(query="退款政策", top_k=5)
    assert req.query == "退款政策"
    assert req.top_k == 5
