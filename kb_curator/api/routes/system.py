"""System health check and status endpoints."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health")
async def health_check() -> dict:
    """Basic health check endpoint."""
    return {
        "status": "ok",
        "service": "kb-curator",
        "version": "0.1.0",
    }


@router.get("/ready")
async def readiness_check() -> dict:
    """Readiness check — verifies external dependencies are reachable."""
    checks: dict[str, str] = {}

    # Check Neo4j
    try:
        from kb_curator.services.graph_store import get_graph_store

        store = get_graph_store()
        await store.verify_connection()
        checks["neo4j"] = "ok"
    except ImportError:
        checks["neo4j"] = "unavailable: neo4j driver not installed"
    except Exception as e:
        checks["neo4j"] = f"error: {e}"

    # Check Redis
    try:
        import redis.asyncio as aioredis

        from kb_curator.core.config import get_settings

        settings = get_settings()
        r = aioredis.from_url(settings.redis.url)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except ImportError:
        checks["redis"] = "unavailable: redis not installed"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    all_ok = all(v == "ok" for v in checks.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "checks": checks,
    }
