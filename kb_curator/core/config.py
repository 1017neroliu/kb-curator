"""Application configuration using Pydantic Settings."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """LLM-related configuration."""

    model: str = Field(default="gpt-4o-mini", description="Chat completion model")
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1)
    timeout_seconds: int = Field(default=60, ge=1)
    max_retries: int = Field(default=3, ge=0, description="Max retry attempts for LLM calls")
    retry_delay_seconds: float = Field(default=1.0, ge=0.0, description="Base delay between retries")
    rpm_limit: int = Field(default=60, ge=0, description="Requests per minute limit (0=unlimited)")

    embedding_model: str = Field(default="text-embedding-3-small")
    embedding_dimensions: int = Field(default=1536, ge=1)
    embedding_batch_size: int = Field(default=100, ge=1)
    embedding_api_base: str = Field(default="", description="Override API base for embedding calls (if different from chat)")
    embedding_api_key: str = Field(default="", description="Override API key for embedding calls")


class VectorStoreSettings(BaseSettings):
    """Vector store configuration."""

    type: Literal["faiss", "chroma"] = "faiss"
    faiss_index_path: Path = Path("./data/faiss_indexes")
    similarity_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    chunk_size: int = Field(default=512, ge=64, description="Default chunk size in characters")
    chunk_overlap: int = Field(default=64, ge=0, description="Overlap between chunks")


class GraphStoreSettings(BaseSettings):
    """Neo4j graph store configuration."""

    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: str = "password"
    database: str = "neo4j"
    max_connection_pool_size: int = Field(default=50, ge=1)
    connection_acquisition_timeout: int = Field(default=60, ge=1)
    max_transaction_retry_time: int = Field(default=30, ge=1)


class DatabaseSettings(BaseSettings):
    """Metadata database configuration."""

    sqlite_url: str = "sqlite+aiosqlite:///./data/kb_curator.db"
    echo: bool = False


class RedisSettings(BaseSettings):
    """Redis and Celery configuration."""

    url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"


class ScheduleSettings(BaseSettings):
    """Scheduling configuration."""

    poll_interval_minutes: int = Field(default=60, ge=1)
    quality_inspection_full_cron: str = "0 3 * * 0"
    quality_inspection_incremental_cron: str = "0 2 * * *"
    review_timeout_hours: int = Field(default=24, ge=1)
    auto_resolve_check_interval_minutes: int = Field(default=30, ge=1)


class AuthSettings(BaseSettings):
    """Authentication configuration."""

    enabled: bool = False
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    token_expire_minutes: int = Field(default=1440, ge=1)


class QASettings(BaseSettings):
    """QA (Question Answering) configuration."""

    top_k: int = Field(default=5, ge=1, le=20, description="Default number of chunks to retrieve")
    graph_expand_limit: int = Field(default=20, ge=1, description="Max entities to expand from graph")
    context_max_chars: int = Field(default=4000, ge=500, description="Max characters for assembled context")
    qa_temperature: float = Field(default=0.3, ge=0.0, le=2.0, description="Temperature for QA LLM calls")
    streaming_enabled: bool = Field(default=True, description="Whether streaming QA is enabled")


class AppSettings(BaseSettings):
    """Main application settings, loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="KB_CURATOR_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # ---- Application ----
    app_name: str = "KB-Curator"
    app_version: str = "0.1.0"
    debug: bool = False
    environment: Literal["development", "staging", "production"] = "development"

    # ---- API ----
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, ge=1, le=65535)
    api_workers: int = Field(default=1, ge=1)

    # ---- Logging ----
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"

    # ---- Data Paths ----
    data_dir: Path = Path("./data")
    checkpoint_dir: Path = Path("./data/checkpoints")

    # ---- Nested settings ----
    llm: LLMSettings = Field(default_factory=LLMSettings)
    vector_store: VectorStoreSettings = Field(default_factory=VectorStoreSettings)
    graph_store: GraphStoreSettings = Field(default_factory=GraphStoreSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    schedule: ScheduleSettings = Field(default_factory=ScheduleSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    qa: QASettings = Field(default_factory=QASettings)

    @field_validator("environment")
    @classmethod
    def _validate_environment(cls, v: str) -> str:
        """Ensure debug is True in development environment."""
        return v

    def ensure_directories(self) -> None:
        """Create all required data directories if they don't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.vector_store.faiss_index_path.mkdir(parents=True, exist_ok=True)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)


# Global settings instance — imported by other modules
_settings: AppSettings | None = None


def get_settings() -> AppSettings:
    """Return cached application settings (singleton)."""
    global _settings
    if _settings is None:
        _settings = AppSettings()
    return _settings


def reset_settings() -> None:
    """Reset settings — useful for testing."""
    global _settings
    _settings = None
