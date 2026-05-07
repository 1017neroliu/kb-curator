"""Review task and decision API routes."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from kb_curator.api.deps import SessionDep
from kb_curator.core.logging import get_logger
from kb_curator.models.schemas import (
    DecisionRead,
    DecisionRequest,
    ReviewTaskRead,
    ReviewTaskStatus,
    ReviewTaskType,
)
from pydantic import BaseModel

from kb_curator.services.crud import (
    create_decision,
    create_review_task,
    get_review_task,
    list_decisions_for_task,
    list_review_tasks,
    update_review_task,
)


class ReviewTaskUpdate(BaseModel):
    """Request body for updating a review task."""
    task_status: ReviewTaskStatus | None = None
    assigned_to: str | None = None


log = get_logger(__name__)
router = APIRouter(prefix="/knowledge-bases/{kb_id}/reviews", tags=["Reviews"])


# ============================================================
# ReviewTask CRUD
# ============================================================


@router.get("", response_model=list[ReviewTaskRead])
async def list_reviews(
    kb_id: str,
    session: SessionDep,
    task_status: ReviewTaskStatus | None = Query(None, alias="status"),
    task_type: ReviewTaskType | None = Query(None, alias="type"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[ReviewTaskRead]:
    """List review tasks for a knowledge base, optionally filtered by status and type."""
    tasks = await list_review_tasks(
        session=session,
        kb_id=kb_id,
        status=task_status.value if task_status else None,
        limit=limit,
        offset=offset,
    )
    results = []
    for t in tasks:
        # Filter by task_type if specified (not handled by CRUD layer)
        if task_type and t.task_type != task_type.value:
            continue
        results.append(_task_to_read(t))
    return results


@router.get("/{task_id}", response_model=ReviewTaskRead)
async def get_review(
    kb_id: str,
    task_id: str,
    session: SessionDep,
) -> ReviewTaskRead:
    """Get a specific review task."""
    task = await get_review_task(session, task_id)
    if not task or task.kb_id != kb_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review task not found")
    return _task_to_read(task)


@router.post("", response_model=ReviewTaskRead, status_code=status.HTTP_201_CREATED)
async def create_review(
    kb_id: str,
    conflict_id: str | None = None,
    task_type: ReviewTaskType = ReviewTaskType.CONFLICT_RESOLUTION,
    title: str = "",
    description: str = "",
    assigned_to: str | None = None,
    session: SessionDep = None,
) -> ReviewTaskRead:
    """Create a new review task."""
    from kb_curator.core.config import get_settings
    s = get_settings()
    auto_resolve_at = datetime.utcnow() + timedelta(hours=s.schedule.review_timeout_hours)

    table = await create_review_task(
        session,
        kb_id=kb_id,
        conflict_id=conflict_id,
        task_type=task_type.value,
        title=title,
        description=description,
        assigned_to=assigned_to,
        auto_resolve_at=auto_resolve_at,
    )
    return _task_to_read(table)


@router.patch("/{task_id}", response_model=ReviewTaskRead)
async def update_review(
    kb_id: str,
    task_id: str,
    body: ReviewTaskUpdate,
    session: SessionDep = None,
) -> ReviewTaskRead:
    """Update a review task (status, assignment)."""
    task = await get_review_task(session, task_id)
    if not task or task.kb_id != kb_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review task not found")

    updates: dict = {}
    if body.task_status is not None:
        updates["status"] = body.task_status.value
        if body.task_status == ReviewTaskStatus.RESOLVED:
            updates["resolved_at"] = datetime.utcnow()
    if body.assigned_to is not None:
        updates["assigned_to"] = body.assigned_to

    if not updates:
        return _task_to_read(task)

    updated = await update_review_task(session, task_id, **updates)
    if not updated:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update review task")
    return _task_to_read(updated)


# ============================================================
# Decision Submission
# ============================================================


@router.post(
    "/{task_id}/decisions",
    response_model=DecisionRead,
    status_code=status.HTTP_201_CREATED,
)
async def submit_decision(
    kb_id: str,
    task_id: str,
    body: DecisionRequest,
    decided_by: str = Query(..., description="Username or ID of the decision maker"),
    session: SessionDep = None,
) -> DecisionRead:
    """Submit a decision for a review task.

    This also transitions the review task to 'resolved' status.
    """
    task = await get_review_task(session, task_id)
    if not task or task.kb_id != kb_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review task not found")

    if task.status in (ReviewTaskStatus.RESOLVED.value, ReviewTaskStatus.EXPIRED.value):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Review task is already {task.status}",
        )

    # Create decision record
    table = await create_decision(
        session,
        review_task_id=task_id,
        decision_type=body.decision_type.value,
        rationale=body.rationale,
        decided_by=decided_by,
        merge_content=body.merge_content,
    )

    # Update review task to resolved
    await update_review_task(
        session,
        task_id,
        status=ReviewTaskStatus.RESOLVED.value,
        resolved_at=datetime.utcnow(),
    )

    return _decision_to_read(table)


@router.get("/{task_id}/decisions", response_model=list[DecisionRead])
async def list_decisions(
    kb_id: str,
    task_id: str,
    session: SessionDep,
) -> list[DecisionRead]:
    """List all decisions for a review task."""
    task = await get_review_task(session, task_id)
    if not task or task.kb_id != kb_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review task not found")

    decisions = await list_decisions_for_task(session, task_id)
    return [_decision_to_read(d) for d in decisions]


# ============================================================
# Conversion helpers
# ============================================================


def _task_to_read(table) -> ReviewTaskRead:
    """Convert ReviewTaskTable to ReviewTaskRead."""
    return ReviewTaskRead(
        id=table.id,
        kb_id=table.kb_id,
        conflict_id=table.conflict_id,
        task_type=ReviewTaskType(table.task_type),
        title=table.title,
        description=table.description,
        status=ReviewTaskStatus(table.status),
        assigned_to=table.assigned_to,
        auto_resolve_at=table.auto_resolve_at,
        created_at=table.created_at,
        resolved_at=table.resolved_at,
    )


def _decision_to_read(table) -> DecisionRead:
    """Convert DecisionTable to DecisionRead."""
    from kb_curator.models.schemas import DecisionType

    return DecisionRead(
        id=table.id,
        review_task_id=table.review_task_id,
        decision_type=DecisionType(table.decision_type),
        rationale=table.rationale,
        decided_by=table.decided_by,
        merge_content=table.merge_content,
        decided_at=table.decided_at,
    )
