"""Quality report API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from kb_curator.api.deps import get_db_session
from kb_curator.core.logging import get_logger
from kb_curator.models.schemas import QualityReportRead, QualityIssue
from kb_curator.services.crud import (
    create_quality_report,
    get_quality_report,
    list_quality_reports,
)
from kb_curator.services.quality_inspector import QualityInspector

log = get_logger(__name__)
router = APIRouter(prefix="/knowledge-bases/{kb_id}/quality", tags=["Quality"])


@router.post("/inspect", response_model=QualityReportRead, status_code=status.HTTP_201_CREATED)
async def run_inspection(
    kb_id: str,
    inspection_type: str = Query(default="incremental", regex="^(full|incremental|targeted)$"),
    entry_ids: str | None = Query(default=None, description="逗号分隔的条目 ID，仅定向巡检时使用"),
    session: Annotated[AsyncSession, Depends(get_db_session)] = None,
) -> QualityReportRead:
    """Run quality inspection and create a report.

    - **full**: 全量巡检，执行所有检查项（过期、低命中率、孤立实体、元数据一致性）
    - **incremental**: 增量巡检，仅执行轻量检查（过期、低命中率），跳过图谱查询
    - **targeted**: 定向巡检，仅检查指定条目（过期、元数据一致性）
    """
    try:
        parsed_entry_ids = entry_ids.split(",") if entry_ids else None
        inspector = QualityInspector(kb_id=kb_id)
        report = await inspector.inspect(
            inspection_type=inspection_type,
            entry_ids=parsed_entry_ids,
        )

        # Save report to database
        issues_data = [
            {
                "entry_id": issue.entry_id,
                "issue_type": issue.issue_type.value,
                "severity": issue.severity.value,
                "detail": issue.detail,
                "suggestion": issue.suggestion,
            }
            for issue in report.issues
        ]

        table = await create_quality_report(
            session,
            kb_id=kb_id,
            inspection_type=inspection_type,
            total_entries=report.total_entries,
            score=report.score,
            issues=issues_data,
        )

        return QualityReportRead(
            id=table.id,
            kb_id=table.kb_id,
            inspection_type=table.inspection_type,
            total_entries=table.total_entries,
            issues=[
                QualityIssue(
                    entry_id=i.get("entry_id", ""),
                    issue_type=i.get("issue_type", "low_hit_rate"),
                    severity=i.get("severity", "warning"),
                    detail=i.get("detail", ""),
                    suggestion=i.get("suggestion", ""),
                )
                for i in issues_data
            ],
            score=table.score,
            inspected_at=table.inspected_at,
        )

    except Exception as e:
        log.error("inspection_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/reports", response_model=list[QualityReportRead])
async def list_reports(
    kb_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[QualityReportRead]:
    """List quality reports for a knowledge base."""
    try:
        reports = await list_quality_reports(
            session=session,
            kb_id=kb_id,
            limit=limit,
            offset=offset,
        )
        return [_table_to_read(r) for r in reports]
    except Exception as e:
        log.error("list_reports_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/reports/{report_id}", response_model=QualityReportRead)
async def get_report(
    kb_id: str,
    report_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> QualityReportRead:
    """Get a specific quality report."""
    try:
        report = await get_quality_report(session, report_id)
        if not report or report.kb_id != kb_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
        return _table_to_read(report)
    except HTTPException:
        raise
    except Exception as e:
        log.error("get_report_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def _table_to_read(table) -> QualityReportRead:
    """Convert QualityReportTable to QualityReportRead."""
    import json
    issues_json = table.issues_json if hasattr(table, 'issues_json') else "[]"
    issues_list = json.loads(issues_json) if issues_json else []
    return QualityReportRead(
        id=table.id,
        kb_id=table.kb_id,
        inspection_type=table.inspection_type,
        total_entries=table.total_entries,
        issues=[
            QualityIssue(
                entry_id=i.get("entry_id", ""),
                issue_type=i.get("issue_type", "low_hit_rate"),
                severity=i.get("severity", "warning"),
                detail=i.get("detail", ""),
                suggestion=i.get("suggestion", ""),
            )
            for i in issues_list
        ],
        score=table.score,
        inspected_at=table.inspected_at,
    )
