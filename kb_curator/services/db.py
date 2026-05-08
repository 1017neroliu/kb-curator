"""SQLite metadata database setup using SQLAlchemy async."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from kb_curator.core.config import get_settings

_engine = None
_session_factory = None


def get_engine():
    """Get or create the async SQLAlchemy engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database.sqlite_url,
            echo=settings.database.echo or settings.debug,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the async session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_session() -> AsyncSession:
    """FastAPI dependency that yields an async database session."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def init_db() -> None:
    """Initialize the database schema."""
    from kb_curator.models.db_tables import Base

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migrations: add columns that may not exist in older databases
        from sqlalchemy import text
        # Check if scan_status column exists in data_sources
        result = await conn.execute(text("PRAGMA table_info(data_sources)"))
        columns = [row[1] for row in result]
        if "scan_status" not in columns:
            await conn.execute(
                text("ALTER TABLE data_sources ADD COLUMN scan_status VARCHAR(32) DEFAULT 'pending'")
            )
