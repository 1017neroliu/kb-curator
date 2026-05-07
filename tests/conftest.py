"""Shared test fixtures for KB-Curator."""

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def _init_test_db():
    """Auto-initialize the database schema before each test.

    This ensures all tables exist when the FastAPI app handles requests.
    Without this, integration/e2e tests that hit API routes will get 500 errors
    because the SQLite database file may not have the schema.
    """
    from kb_curator.services.db import init_db, get_engine
    await init_db()
    yield
    # Clean up: drop all tables so tests don't interfere with each other
    engine = get_engine()
    async with engine.begin() as conn:
        from kb_curator.models.db_tables import Base
        await conn.run_sync(Base.metadata.drop_all)
