"""Celery worker entry point."""

from __future__ import annotations

from celery import Celery

from kb_curator.core.config import get_settings


def create_celery_app() -> Celery:
    """Create and configure the Celery application."""
    settings = get_settings()
    app = Celery(
        "kb_curator",
        broker=settings.redis.celery_broker_url,
        backend=settings.redis.celery_result_backend,
    )
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
    )
    return app


celery_app = create_celery_app()


@celery_app.task(name="kb_curator.run_pipeline")
def run_pipeline_task(event_data: dict) -> dict:
    """Celery task: run the agent pipeline for a change event.

    This is a placeholder that will be implemented in Phase 4.
    """
    # TODO: Implement in Phase 4.7 — LangGraph Agent Orchestration
    return {"status": "not_implemented", "event_id": event_data.get("id")}


def run_worker() -> None:
    """Run the Celery worker (entry point for poetry script)."""
    celery_app.worker_main(["worker", "--loglevel=info"])
