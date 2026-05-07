"""QA (Question Answering) API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from kb_curator.core.config import get_settings
from kb_curator.models.schemas import QARequest, QAResponse
from kb_curator.services.qa_service import get_qa_service

router = APIRouter(prefix="/qa", tags=["QA"])


@router.post("/ask", response_model=QAResponse)
async def ask_question(request: QARequest) -> QAResponse:
    """Non-streaming QA endpoint: returns the full answer at once."""
    settings = get_settings()
    if not settings.qa.streaming_enabled and not request.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    if not request.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    qa_svc = get_qa_service()
    try:
        return await qa_svc.answer(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"问答处理失败: {e}")


@router.post("/ask/stream")
async def ask_question_stream(request: QARequest) -> StreamingResponse:
    """Streaming QA endpoint: returns SSE events with sources and tokens."""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    settings = get_settings()
    if not settings.qa.streaming_enabled:
        raise HTTPException(status_code=400, detail="流式问答未启用")

    qa_svc = get_qa_service()
    return StreamingResponse(
        qa_svc.answer_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
