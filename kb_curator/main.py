"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from kb_curator.api.routes import (
    agent,
    auth,
    conflicts,
    entries,
    events,
    knowledge_bases,
    knowledge_graph,
    quality,
    reviews,
    sources,
    system,
)
from kb_curator.core.config import get_settings
from kb_curator.core.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown logic."""
    settings = get_settings()
    configure_logging()

    # Ensure data directories exist
    settings.ensure_directories()

    # Initialize database
    from kb_curator.services.db import init_db
    await init_db()

    yield

    # Cleanup
    try:
        from kb_curator.services.graph_store import get_graph_store
        store = get_graph_store()
        await store.close()
    except Exception:
        pass


API_DESCRIPTION = """
## KB-Curator API

知识库"活文档"维护 Agent 的 RESTful API。

### 核心流程

1. **知识库管理** — 创建/删除知识库，查看概览统计
2. **数据源管理** — 注册文档来源，配置轮询策略
3. **知识条目** — CRUD + 语义搜索，版本自动递增
4. **变更事件** — 文档变化检测，按类型分类（新信息/策略变更/矛盾/纠正/冗余）
5. **冲突检测** — 语义/结构/时序三种冲突类型
6. **审核决策** — 人工审核任务 + 6 种决策类型（accept_new/keep_old/merge/ignore/delete/archive）
7. **质量巡检** — 全量/增量/定向巡检，质量评分 + 问题列表
8. **知识图谱** — 实体/关系 CRUD，图谱统计
9. **Agent** — LangGraph 状态机触发/恢复/状态查询

### 认证

默认认证关闭（`KB_CURATOR_AUTH_ENABLED=false`）。
启用后，通过 `POST /api/v1/auth/token` 获取 JWT Token，
后续请求携带 `Authorization: Bearer <token>`。

### 多租户

所有数据通过 `kb_id` 字段隔离，确保知识库间数据不串扰。
"""

OPENAPI_TAGS = [
    {"name": "system", "description": "系统健康检查与就绪探针"},
    {"name": "auth", "description": "JWT Token 签发"},
    {"name": "Knowledge Bases", "description": "知识库管理（创建/删除/概览）"},
    {"name": "Entries", "description": "知识条目 CRUD + 语义搜索"},
    {"name": "Sources", "description": "数据源管理（注册/轮询配置/启停）"},
    {"name": "Change Events", "description": "变更事件（检测/分类/时间线）"},
    {"name": "Conflicts", "description": "冲突检测（语义/结构/时序）"},
    {"name": "Reviews", "description": "审核任务 + 人工决策"},
    {"name": "Quality", "description": "质量巡检 + 报告"},
    {"name": "Knowledge Graph", "description": "知识图谱（实体/关系/统计）"},
    {"name": "Agent", "description": "LangGraph Agent 触发/恢复/状态"},
]


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=API_DESCRIPTION,
        lifespan=lifespan,
        openapi_tags=OPENAPI_TAGS,
        contact={
            "name": "KB-Curator Team",
        },
        license_info={
            "name": "MIT",
        },
        servers=[
            {"url": "/api/v1", "description": "API v1"},
        ],
    )

    # Register routers
    app.include_router(system.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(knowledge_bases.router, prefix="/api/v1")
    app.include_router(entries.router, prefix="/api/v1")
    app.include_router(sources.router, prefix="/api/v1")
    app.include_router(events.router, prefix="/api/v1")
    app.include_router(conflicts.router, prefix="/api/v1")
    app.include_router(reviews.router, prefix="/api/v1")
    app.include_router(quality.router, prefix="/api/v1")
    app.include_router(knowledge_graph.router, prefix="/api/v1")
    app.include_router(agent.router, prefix="/api/v1")

    return app


# Module-level app instance for uvicorn
app = create_app()


def run_api() -> None:
    """Run the API server (entry point for poetry script)."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "kb_curator.main:app",
        host=settings.api_host,
        port=settings.api_port,
        workers=settings.api_workers,
        reload=settings.debug,
    )
