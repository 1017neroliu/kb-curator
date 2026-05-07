"""Review task management service."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from kb_curator.core.logging import get_logger
from kb_curator.models.schemas import DecisionType, ReviewTaskStatus
from kb_curator.services.crud import (
    list_expired_review_tasks,
    update_review_task,
)
from kb_curator.services.db import get_session

log = get_logger(__name__)


async def auto_resolve_expired_reviews() -> dict[str, Any]:
    """Auto-resolve expired review tasks using conservative strategy.

    On timeout, keeps old knowledge and ignores new information.

    Returns:
        Summary of auto-resolution results.
    """
    results = {
        "expired_tasks": 0,
        "resolved": 0,
        "errors": [],
    }

    try:
        async for session in get_session():
            expired = await list_expired_review_tasks(session)

            for task in expired:
                results["expired_tasks"] += 1
                try:
                    await update_review_task(
                        session,
                        task.id,
                        status=ReviewTaskStatus.EXPIRED.value,
                        resolved_at=datetime.utcnow(),
                    )
                    results["resolved"] += 1
                    log.info(
                        "review_task_auto_resolved",
                        task_id=task.id,
                        kb_id=task.kb_id,
                        resolution=DecisionType.KEEP_OLD.value,
                    )
                except Exception as e:
                    log.error("auto_resolve_failed", task_id=task.id, error=str(e))
                    results["errors"].append(str(e))

    except Exception as e:
        log.error("auto_resolve_expired_reviews_failed", error=str(e))
        results["errors"].append(str(e))

    log.info("auto_resolve_completed", **results)
    return results
