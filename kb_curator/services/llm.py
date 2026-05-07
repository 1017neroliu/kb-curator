"""LLM service wrapper using LiteLLM with retry and rate limiting."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import litellm

from kb_curator.core.config import get_settings
from kb_curator.core.logging import get_logger

log = get_logger(__name__)


class RateLimiter:
    """Simple token-bucket rate limiter for LLM API calls."""

    def __init__(self, rpm_limit: int = 0) -> None:
        """Initialize rate limiter.

        Args:
            rpm_limit: Requests per minute limit. 0 means unlimited.
        """
        self._rpm_limit = rpm_limit
        self._timestamps: list[float] = []

    async def acquire(self) -> None:
        """Wait until a request slot is available."""
        if self._rpm_limit <= 0:
            return

        now = time.monotonic()
        # Remove timestamps older than 60 seconds
        cutoff = now - 60.0
        self._timestamps = [t for t in self._timestamps if t > cutoff]

        if len(self._timestamps) >= self._rpm_limit:
            # Wait until the oldest request expires
            wait_time = self._timestamps[0] - cutoff + 0.01
            log.debug("rate_limiter_waiting", wait_seconds=round(wait_time, 2))
            await asyncio.sleep(wait_time)

        self._timestamps.append(time.monotonic())


# Global rate limiter
_rate_limiter: RateLimiter | None = None


def _get_rate_limiter() -> RateLimiter:
    """Get or create the global rate limiter."""
    global _rate_limiter
    if _rate_limiter is None:
        settings = get_settings()
        _rate_limiter = RateLimiter(rpm_limit=settings.llm.rpm_limit)
    return _rate_limiter


async def completion(
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    response_format: dict | None = None,
    max_retries: int | None = None,
    **kwargs: Any,
) -> str:
    """Send a chat completion request via LiteLLM with retry and rate limiting.

    Args:
        messages: List of message dicts with 'role' and 'content'.
        model: Override the default model.
        temperature: Override the default temperature.
        max_tokens: Override the default max_tokens.
        response_format: Optional response format (e.g., JSON mode).
        max_retries: Override the default max retries.
        **kwargs: Additional arguments passed to litellm.acompletion.

    Returns:
        The assistant's response content as a string.

    Raises:
        litellm.RateLimitError: If all retries are exhausted due to rate limits.
        litellm.APIError: If all retries are exhausted due to API errors.
    """
    settings = get_settings()
    retries = max_retries if max_retries is not None else settings.llm.max_retries
    rate_limiter = _get_rate_limiter()

    params: dict[str, Any] = {
        "model": model or settings.llm.model,
        "messages": messages,
        "temperature": temperature if temperature is not None else settings.llm.temperature,
        "max_tokens": max_tokens or settings.llm.max_tokens,
        "timeout": settings.llm.timeout_seconds,
    }
    if response_format:
        params["response_format"] = response_format
    params.update(kwargs)

    log.debug("llm_completion_start", model=params["model"],
              message_count=len(messages))

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            await rate_limiter.acquire()
            response = await litellm.acompletion(**params)
            content = response.choices[0].message.content or ""

            usage = response.usage
            log.debug("llm_completion_done", model=params["model"],
                      attempt=attempt,
                      response_tokens=usage.completion_tokens if usage else 0,
                      prompt_tokens=usage.prompt_tokens if usage else 0)
            return content

        except litellm.RateLimitError as e:
            last_error = e
            if attempt < retries:
                delay = settings.llm.retry_delay_seconds * (2 ** attempt)
                log.warning("llm_rate_limited", model=params["model"],
                            attempt=attempt, retry_in=delay)
                await asyncio.sleep(delay)
            else:
                log.error("llm_rate_limit_exhausted", model=params["model"],
                          attempts=attempt + 1)

        except (litellm.APIConnectionError, litellm.Timeout) as e:
            last_error = e
            if attempt < retries:
                delay = settings.llm.retry_delay_seconds * (2 ** attempt)
                log.warning("llm_connection_error", model=params["model"],
                            attempt=attempt, retry_in=delay, error=str(e))
                await asyncio.sleep(delay)
            else:
                log.error("llm_retries_exhausted", model=params["model"],
                          attempts=attempt + 1, error=str(e))

        except litellm.APIError as e:
            # Don't retry on non-transient errors (4xx except 429)
            last_error = e
            log.error("llm_api_error", model=params["model"],
                      status_code=getattr(e, 'status_code', None),
                      error=str(e))
            raise

    raise last_error or RuntimeError("LLM call failed with no specific error")


async def embedding(text: str | list[str], model: str | None = None) -> list[float] | list[list[float]]:
    """Generate embeddings via LiteLLM.

    Args:
        text: A single string or list of strings to embed.
        model: Override the default embedding model.

    Returns:
        A single embedding vector (if input was a string) or a list of vectors.
    """
    settings = get_settings()
    model = model or settings.llm.embedding_model
    rate_limiter = _get_rate_limiter()
    is_single = isinstance(text, str)
    input_texts = [text] if is_single else text

    # Build embedding-specific kwargs
    embed_kwargs: dict[str, Any] = {}
    if settings.llm.embedding_api_base:
        embed_kwargs["api_base"] = settings.llm.embedding_api_base
    if settings.llm.embedding_api_key:
        embed_kwargs["api_key"] = settings.llm.embedding_api_key

    # Process in batches if needed
    batch_size = settings.llm.embedding_batch_size
    all_embeddings: list[list[float]] = []

    for i in range(0, len(input_texts), batch_size):
        batch = input_texts[i:i + batch_size]
        await rate_limiter.acquire()

        response = await litellm.aembedding(model=model, input=batch, encoding_format="float", **embed_kwargs)
        batch_embeddings = [item["embedding"] for item in response.data]
        all_embeddings.extend(batch_embeddings)

    if is_single:
        return all_embeddings[0]
    return all_embeddings


async def json_completion(
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float | None = None,
    max_retries: int | None = None,
    **kwargs: Any,
) -> str:
    """Send a chat completion request that returns JSON.

    Convenience wrapper that forces JSON response format.

    Args:
        messages: List of message dicts.
        model: Override the default model.
        temperature: Override the default temperature.
        max_retries: Override the default max retries.
        **kwargs: Additional arguments.

    Returns:
        The raw JSON string from the assistant's response.
    """
    return await completion(
        messages=messages,
        model=model,
        temperature=temperature,
        response_format={"type": "json_object"},
        max_retries=max_retries,
        **kwargs,
    )
