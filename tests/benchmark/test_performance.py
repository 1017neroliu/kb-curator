"""Performance benchmark tests for KB-Curator API endpoints.

These tests measure response times for key operations under load.
They are NOT part of the regular CI suite — run them explicitly:

    pytest tests/benchmark/ -v -s

Each test creates a fresh in-memory SQLite database and measures
round-trip latency for batched operations.
"""

from __future__ import annotations

import os
import statistics
import time

import pytest
from httpx import ASGITransport, AsyncClient

os.environ["KB_CURATOR_AUTH_ENABLED"] = "false"
os.environ["KB_CURATOR_DEBUG"] = "false"

from kb_curator.main import app


KB_ID = "bench_kb"
SOURCE_ID = "bench_src"


@pytest.fixture
async def client():
    """Async HTTP client for benchmarking."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def setup_prerequisites(client: AsyncClient) -> None:
    """Create KB and source for benchmarks."""
    await client.post(f"/api/v1/knowledge-bases/{KB_ID}")
    await client.post(
        f"/api/v1/knowledge-bases/{KB_ID}/sources",
        json={
            "kb_id": KB_ID,
            "name": "Bench Source",
            "source_type": "file",
            "connection_config": {"path": "/bench"},
        },
    )


class BenchmarkResult:
    """Helper to collect and report benchmark metrics."""

    def __init__(self, name: str):
        self.name = name
        self.times: list[float] = []

    def record(self, elapsed: float) -> None:
        self.times.append(elapsed)

    def report(self) -> dict:
        if not self.times:
            return {"name": self.name, "count": 0}
        return {
            "name": self.name,
            "count": len(self.times),
            "mean_ms": round(statistics.mean(self.times) * 1000, 2),
            "median_ms": round(statistics.median(self.times) * 1000, 2),
            "p95_ms": round(sorted(self.times)[int(len(self.times) * 0.95)] * 1000, 2),
            "min_ms": round(min(self.times) * 1000, 2),
            "max_ms": round(max(self.times) * 1000, 2),
        }


# ============================================================
# Benchmark: Entry creation throughput
# ============================================================


class TestEntryCreationBenchmark:
    """Benchmark entry creation and listing performance."""

    @pytest.mark.asyncio
    async def test_create_entries_batch(self, client: AsyncClient):
        """Benchmark: Create 50 entries and measure individual latency."""
        await setup_prerequisites(client)
        bench = BenchmarkResult("create_entry")

        for i in range(50):
            start = time.monotonic()
            resp = await client.post(
                f"/api/v1/knowledge-bases/{KB_ID}/entries",
                json={
                    "kb_id": KB_ID,
                    "title": f"Bench Entry {i}",
                    "content": f"Benchmark content for entry {i}. " * 10,
                    "source_id": SOURCE_ID,
                    "tags": ["bench", f"tag-{i}"],
                },
            )
            elapsed = time.monotonic() - start
            assert resp.status_code == 201
            bench.record(elapsed)

        result = bench.report()
        print(f"\n{result}")
        # Entry creation should be under 100ms per entry
        assert result["median_ms"] < 200, f"Entry creation too slow: {result['median_ms']}ms"

    @pytest.mark.asyncio
    async def test_list_entries_pagination(self, client: AsyncClient):
        """Benchmark: List entries with pagination."""
        await setup_prerequisites(client)

        # Create 50 entries
        for i in range(50):
            await client.post(
                f"/api/v1/knowledge-bases/{KB_ID}/entries",
                json={
                    "kb_id": KB_ID,
                    "title": f"List Bench {i}",
                    "content": f"Content {i}",
                    "source_id": SOURCE_ID,
                },
            )

        bench = BenchmarkResult("list_entries")
        for offset in range(0, 50, 10):
            start = time.monotonic()
            resp = await client.get(
                f"/api/v1/knowledge-bases/{KB_ID}/entries",
                params={"limit": 10, "offset": offset},
            )
            elapsed = time.monotonic() - start
            assert resp.status_code == 200
            bench.record(elapsed)

        result = bench.report()
        print(f"\n{result}")
        # Listing should be fast
        assert result["median_ms"] < 100, f"Listing too slow: {result['median_ms']}ms"

    @pytest.mark.asyncio
    async def test_entry_count(self, client: AsyncClient):
        """Benchmark: Entry count endpoint."""
        await setup_prerequisites(client)

        # Create entries
        for i in range(30):
            await client.post(
                f"/api/v1/knowledge-bases/{KB_ID}/entries",
                json={
                    "kb_id": KB_ID,
                    "title": f"Count Bench {i}",
                    "content": f"Content {i}",
                    "source_id": SOURCE_ID,
                },
            )

        bench = BenchmarkResult("entry_count")
        for _ in range(20):
            start = time.monotonic()
            resp = await client.get(
                f"/api/v1/knowledge-bases/{KB_ID}/entries/count"
            )
            elapsed = time.monotonic() - start
            assert resp.status_code == 200
            bench.record(elapsed)

        result = bench.report()
        print(f"\n{result}")
        assert result["median_ms"] < 50, f"Count too slow: {result['median_ms']}ms"


# ============================================================
# Benchmark: Review task operations
# ============================================================


class TestReviewBenchmark:
    """Benchmark review task creation and decision submission."""

    @pytest.mark.asyncio
    async def test_review_and_decision_throughput(self, client: AsyncClient):
        """Benchmark: Create review + submit decision cycle."""
        await setup_prerequisites(client)

        bench_create = BenchmarkResult("create_review")
        bench_decide = BenchmarkResult("submit_decision")

        for i in range(20):
            # Create review
            start = time.monotonic()
            resp = await client.post(
                f"/api/v1/knowledge-bases/{KB_ID}/reviews",
                params={
                    "task_type": "conflict_resolution",
                    "title": f"Bench Review {i}",
                    "description": f"Benchmark review {i}",
                },
            )
            elapsed = time.monotonic() - start
            assert resp.status_code == 201
            bench_create.record(elapsed)
            task_id = resp.json()["id"]

            # Submit decision
            start = time.monotonic()
            resp = await client.post(
                f"/api/v1/knowledge-bases/{KB_ID}/reviews/{task_id}/decisions",
                json={
                    "decision_type": "accept_new",
                    "rationale": f"Bench decision {i}",
                },
                params={"decided_by": "bench_admin"},
            )
            elapsed = time.monotonic() - start
            assert resp.status_code == 201
            bench_decide.record(elapsed)

        create_result = bench_create.report()
        decide_result = bench_decide.report()
        print(f"\nCreate: {create_result}")
        print(f"Decide: {decide_result}")

        assert create_result["median_ms"] < 100
        assert decide_result["median_ms"] < 100


# ============================================================
# Benchmark: Change events bulk operations
# ============================================================


class TestEventsBenchmark:
    """Benchmark change event creation and listing."""

    @pytest.mark.asyncio
    async def test_events_bulk_create_and_list(self, client: AsyncClient):
        """Benchmark: Create 50 events and list with filtering."""
        await setup_prerequisites(client)

        bench_create = BenchmarkResult("create_event")
        for i in range(50):
            start = time.monotonic()
            resp = await client.post(
                f"/api/v1/knowledge-bases/{KB_ID}/events",
                json={
                    "kb_id": KB_ID,
                    "source_id": SOURCE_ID,
                    "change_type": ["new_info", "policy_change", "correction"][i % 3],
                    "title": f"Bench Event {i}",
                    "content_after": f"New content {i}",
                },
            )
            elapsed = time.monotonic() - start
            assert resp.status_code == 201
            bench_create.record(elapsed)

        # Benchmark listing with filter
        bench_list = BenchmarkResult("list_events_filtered")
        for _ in range(10):
            start = time.monotonic()
            resp = await client.get(
                f"/api/v1/knowledge-bases/{KB_ID}/events",
                params={"change_type": "new_info", "limit": 20},
            )
            elapsed = time.monotonic() - start
            assert resp.status_code == 200
            bench_list.record(elapsed)

        create_result = bench_create.report()
        list_result = bench_list.report()
        print(f"\nCreate: {create_result}")
        print(f"List: {list_result}")

        assert create_result["median_ms"] < 100
        assert list_result["median_ms"] < 100


# ============================================================
# Benchmark: Quality inspection
# ============================================================


class TestQualityBenchmark:
    """Benchmark quality inspection performance."""

    @pytest.mark.asyncio
    async def test_quality_inspection(self, client: AsyncClient):
        """Benchmark: Run quality inspection on a populated KB."""
        await setup_prerequisites(client)

        # Create entries
        for i in range(20):
            await client.post(
                f"/api/v1/knowledge-bases/{KB_ID}/entries",
                json={
                    "kb_id": KB_ID,
                    "title": f"Quality Bench {i}",
                    "content": f"Content {i}",
                    "source_id": SOURCE_ID,
                },
            )

        bench = BenchmarkResult("quality_inspection")
        for _ in range(5):
            start = time.monotonic()
            resp = await client.post(
                f"/api/v1/knowledge-bases/{KB_ID}/quality/inspect",
                params={"inspection_type": "incremental"},
            )
            elapsed = time.monotonic() - start
            assert resp.status_code == 201
            bench.record(elapsed)

        result = bench.report()
        print(f"\n{result}")
        # Quality inspection should complete within reasonable time
        assert result["median_ms"] < 2000, f"Inspection too slow: {result['median_ms']}ms"
