"""Agent API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from kb_curator.core.logging import get_logger
from kb_curator.models.schemas import ExecutionResult

log = get_logger(__name__)
router = APIRouter(prefix="/agent", tags=["Agent"])


@router.post("/run", response_model=ExecutionResult)
async def run_agent(
    kb_id: str,
    change_event_id: str | None = None,
    change_type: str | None = None,
    entry_id: str | None = None,
) -> ExecutionResult:
    """Trigger the agent to process a change event or knowledge entry.

    If entry_id is provided, the agent will load the entry content and
    run the full extraction pipeline (classify -> extract -> detect conflicts -> update).
    """
    try:
        from kb_curator.agents.agent_runner import get_agent_runner

        runner = get_agent_runner(kb_id)

        config = {
            "kb_id": kb_id,
            "change_event_id": change_event_id,
            "change_type": change_type,
            "entry_id": entry_id,
        }

        result = await runner.run(config)

        return ExecutionResult(
            success=result.get("execution_result", {}).get("success", False),
            status="completed" if not result.get("has_conflict") else "awaiting_review",
            operations_completed=result.get("execution_result", {}).get("entities", 0),
            errors=result.get("errors", []),
        )
    except Exception as e:
        log.error("agent_run_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/resume", response_model=ExecutionResult)
async def resume_agent(
    thread_id: str,
    kb_id: str,
    decision_type: str,
    rationale: str,
) -> ExecutionResult:
    """Resume an interrupted agent with human decision."""
    try:
        from kb_curator.agents.agent_runner import get_agent_runner
        
        runner = get_agent_runner(kb_id)
        
        human_decision = {
            "decision_type": decision_type,
            "rationale": rationale,
        }
        
        result = await runner.resume(thread_id, human_decision)
        
        return ExecutionResult(
            success=result.get("execution_result", {}).get("success", False),
            status="completed",
            operations_completed=len(result.get("text_chunks", [])),
            errors=result.get("errors", []),
        )
    except Exception as e:
        log.error("agent_resume_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/state/{thread_id}")
async def get_agent_state(
    thread_id: str,
    kb_id: str,
) -> dict[str, Any]:
    """Get the current state of an agent thread."""
    try:
        from kb_curator.agents.agent_runner import get_agent_runner
        
        runner = get_agent_runner(kb_id)
        state = runner.get_state(thread_id)
        
        if state is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
        
        return state
    except HTTPException:
        raise
    except Exception as e:
        log.error("get_state_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
