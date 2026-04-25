"""Token rate limiter using token bucket algorithm."""
import threading
import time
from typing import Any, TypeVar

from app.core.resilience import RateLimitError
from app.configs.logger import logger

T = TypeVar("T")


class TokenRateLimiter:
    """Token bucket rate limiter for LLM API calls.

    Algorithm:
        - Bucket is refilled at a constant rate (rate tokens per second)
        - Each acquire() consumes one token
        - If bucket is empty, acquire() blocks or raises RateLimitError

    Usage:
        limiter = TokenRateLimiter(rate=10, per_seconds=1.0)  # 10 requests per second
        limiter.acquire()  # blocks until token available
    """

    def __init__(
        self,
        rate: float,
        per_seconds: float = 1.0,
        capacity: float | None = None,
    ):
        """Initialize the token bucket rate limiter.

        Args:
            rate: Number of tokens added per period
            per_seconds: Length of the period in seconds
            capacity: Maximum tokens in bucket (defaults to rate)
        """
        self.rate = rate
        self.per_seconds = per_seconds
        self.capacity = capacity if capacity is not None else rate
        self._tokens = float(self.capacity)
        self._last_refill_time = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill_time
        tokens_to_add = elapsed * (self.rate / self.per_seconds)
        self._tokens = min(self.capacity, self._tokens + tokens_to_add)
        self._last_refill_time = now

    def _consume(self, tokens: float = 1.0) -> bool:
        """Attempt to consume tokens from the bucket.

        Args:
            tokens: Number of tokens to consume

        Returns:
            True if tokens were consumed, False otherwise
        """
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    def acquire(self, timeout: float | None = None) -> bool:
        """Acquire a token, waiting if necessary.

        Args:
            timeout: Maximum seconds to wait. None means wait forever.

        Returns:
            True when token was acquired

        Raises:
            RateLimitError: If timeout is exceeded
        """
        deadline = time.monotonic() + timeout if timeout is not None else None

        while True:
            with self._lock:
                if self._consume():
                    return True

            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RateLimitError(
                        f"Rate limit exceeded: timeout after {timeout}s waiting for token"
                    )
                sleep_time = min(remaining, 0.1)
            else:
                sleep_time = 0.1

            time.sleep(sleep_time)

    def is_available(self) -> bool:
        """Check if a token is immediately available without blocking.

        Returns:
            True if a token can be acquired without waiting
        """
        with self._lock:
            self._refill()
            return self._tokens >= 1.0

    @property
    def available_tokens(self) -> float:
        """Current number of available tokens."""
        with self._lock:
            self._refill()
            return self._tokens


class TokenRateLimiterMiddleware:
    """Middleware that enforces rate limiting before LLM calls.

    Wraps a TokenRateLimiter and integrates with the middleware pipeline.
    """

    def __init__(self, rate_limiter: TokenRateLimiter):
        """Initialize the rate limit middleware.

        Args:
            rate_limiter: The TokenRateLimiter instance to use
        """
        self.rate_limiter = rate_limiter

    def before_llm(self, context: dict[str, Any]) -> dict[str, Any]:
        """Acquire rate limit token before LLM call.

        Args:
            context: LLM context dictionary

        Returns:
            Unmodified context

        Raises:
            RateLimitError: If rate limit cannot be acquired within timeout
        """
        self.rate_limiter.acquire(timeout=5.0)
        return context
