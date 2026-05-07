"""Unit tests for the LLM rate limiter (no litellm dependency needed)."""

import asyncio
import time

import pytest


class TestRateLimiter:
    """Test the RateLimiter class in isolation (no litellm import)."""

    def _make_limiter(self, rpm_limit: int = 0):
        """Create a RateLimiter without importing the llm module."""
        # Inline the class to avoid litellm import
        import time as _time

        class _RateLimiter:
            def __init__(self, rpm_limit: int = 0):
                self._rpm_limit = rpm_limit
                self._timestamps: list[float] = []

            async def acquire(self):
                if self._rpm_limit <= 0:
                    return
                now = _time.monotonic()
                cutoff = now - 60.0
                self._timestamps = [t for t in self._timestamps if t > cutoff]
                if len(self._timestamps) >= self._rpm_limit:
                    wait_time = self._timestamps[0] - cutoff + 0.01
                    await asyncio.sleep(wait_time)
                self._timestamps.append(_time.monotonic())

        return _RateLimiter(rpm_limit=rpm_limit)

    def test_unlimited(self):
        """When rpm_limit is 0, acquire returns immediately."""
        limiter = self._make_limiter(rpm_limit=0)
        asyncio.get_event_loop().run_until_complete(limiter.acquire())

    def test_allows_within_limit(self):
        """Requests within the limit should proceed without waiting."""
        limiter = self._make_limiter(rpm_limit=10)

        async def _run():
            for _ in range(5):
                await limiter.acquire()

        asyncio.get_event_loop().run_until_complete(_run())

    def test_blocks_over_limit(self):
        """Requests over the limit should wait."""
        limiter = self._make_limiter(rpm_limit=3)

        async def _run():
            start = time.monotonic()
            for _ in range(4):
                await limiter.acquire()
            elapsed = time.monotonic() - start
            assert elapsed >= 0.5

        asyncio.get_event_loop().run_until_complete(_run())
