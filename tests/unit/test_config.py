"""Unit tests for the configuration system."""

import pytest

from kb_curator.core.config import (
    AppSettings,
    AuthSettings,
    DatabaseSettings,
    GraphStoreSettings,
    LLMSettings,
    RedisSettings,
    ScheduleSettings,
    VectorStoreSettings,
    get_settings,
    reset_settings,
)


@pytest.fixture(autouse=True)
def _reset_settings():
    """Reset settings before each test."""
    reset_settings()
    yield
    reset_settings()


class TestLLMSettings:
    def test_defaults(self):
        s = LLMSettings()
        assert s.model == "gpt-4o-mini"
        assert s.temperature == 0.0
        assert s.max_retries == 3
        assert s.retry_delay_seconds == 1.0
        assert s.rpm_limit == 60
        assert s.embedding_model == "text-embedding-3-small"
        assert s.embedding_dimensions == 1536
        assert s.embedding_batch_size == 100

    def test_validation_temperature(self):
        with pytest.raises(Exception):
            LLMSettings(temperature=3.0)
        with pytest.raises(Exception):
            LLMSettings(temperature=-0.1)


class TestVectorStoreSettings:
    def test_defaults(self):
        s = VectorStoreSettings()
        assert s.type == "faiss"
        assert s.similarity_threshold == 0.85
        assert s.chunk_size == 512
        assert s.chunk_overlap == 64


class TestGraphStoreSettings:
    def test_defaults(self):
        s = GraphStoreSettings()
        assert s.uri == "bolt://localhost:7687"
        assert s.max_connection_pool_size == 50


class TestScheduleSettings:
    def test_defaults(self):
        s = ScheduleSettings()
        assert s.review_timeout_hours == 24
        assert s.poll_interval_minutes == 60
        assert s.auto_resolve_check_interval_minutes == 30


class TestAppSettings:
    def test_defaults(self):
        s = AppSettings()
        assert s.app_name == "KB-Curator"
        assert s.debug is False
        assert s.environment == "development"

    def test_nested_settings(self):
        s = AppSettings()
        assert isinstance(s.llm, LLMSettings)
        assert isinstance(s.vector_store, VectorStoreSettings)
        assert isinstance(s.graph_store, GraphStoreSettings)
        assert isinstance(s.database, DatabaseSettings)
        assert isinstance(s.redis, RedisSettings)
        assert isinstance(s.schedule, ScheduleSettings)
        assert isinstance(s.auth, AuthSettings)

    def test_nested_access(self):
        s = AppSettings()
        assert s.llm.model == "gpt-4o-mini"
        assert s.graph_store.uri == "bolt://localhost:7687"
        assert s.schedule.review_timeout_hours == 24

    def test_singleton(self):
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_settings_from_env(self, monkeypatch):
        monkeypatch.setenv("KB_CURATOR_DEBUG", "true")
        monkeypatch.setenv("KB_CURATOR_API_PORT", "9000")
        s = AppSettings()
        assert s.debug is True
        assert s.api_port == 9000

    def test_ensure_directories(self, tmp_path):
        s = AppSettings(
            data_dir=tmp_path / "data",
            checkpoint_dir=tmp_path / "checkpoints",
        )
        s.vector_store.faiss_index_path = tmp_path / "faiss"
        s.ensure_directories()
        assert (tmp_path / "data").is_dir()
        assert (tmp_path / "checkpoints").is_dir()
        assert (tmp_path / "faiss").is_dir()

    def test_api_port_validation(self):
        with pytest.raises(Exception):
            AppSettings(api_port=0)
        with pytest.raises(Exception):
            AppSettings(api_port=70000)
