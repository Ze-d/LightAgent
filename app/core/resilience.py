"""Resilience utilities for agent execution: timeout, retry, and circuit breaker."""
import time
from typing import Any, Callable, TypeVar

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    RetryError,
)

from app.configs.logger import logger


T = TypeVar("T")


class TimeoutError(Exception):
    """Raised when a tool or LLM call exceeds its timeout."""
    pass


class RateLimitError(Exception):
    """Raised when rate limit is exceeded (HTTP 429)."""
    pass


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is in OPEN state."""
    pass


class CircuitBreaker:
    """Circuit breaker pattern implementation for fault tolerance.

    States:
        - CLOSED: Normal operation, requests pass through
        - OPEN: Failures exceeded threshold, requests are blocked
        - HALF_OPEN: After timeout, allows one test request

    Transitions:
        CLOSED -> OPEN: when failures >= failure_threshold
        OPEN -> HALF_OPEN: when timeout elapses
        HALF_OPEN -> CLOSED: when test request succeeds
        HALF_OPEN -> OPEN: when test request fails
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout_seconds: float = 60.0,
        name: str = "default",
    ):
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.name = name
        self._failures = 0
        self._last_failure_time: float | None = None
        self._state = self.CLOSED

    @property
    def state(self) -> str:
        if self._state == self.OPEN and self._should_attempt_reset():
            self._state = self.HALF_OPEN
            logger.info(f"Circuit breaker '{self.name}' transitioned to HALF_OPEN")
        return self._state

    def _should_attempt_reset(self) -> bool:
        if self._last_failure_time is None:
            return True
        return time.time() - self._last_failure_time >= self.timeout_seconds

    def record_success(self) -> None:
        if self._state == self.HALF_OPEN:
            self._state = self.CLOSED
            self._failures = 0
            logger.info(f"Circuit breaker '{self.name}' transitioned to CLOSED")

    def record_failure(self) -> None:
        self._failures += 1
        self._last_failure_time = time.time()
        if self._failures >= self.failure_threshold:
            if self._state != self.OPEN:
                self._state = self.OPEN
                logger.warning(
                    f"Circuit breaker '{self.name}' transitioned to OPEN "
                    f"(failures={self._failures})"
                )

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        if self.state == self.OPEN:
            raise CircuitBreakerOpenError(
                f"Circuit breaker '{self.name}' is OPEN"
            )
        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise


def with_timeout(
    func: Callable[..., T],
    timeout_seconds: float,
    *args: Any,
    **kwargs: Any,
) -> T:
    """Execute a synchronous function with a timeout using threading.

    Args:
        func: Synchronous function to execute
        timeout_seconds: Maximum seconds to wait
        *args: Positional arguments for func
        **kwargs: Keyword arguments for func

    Returns:
        Result of func

    Raises:
        TimeoutError: If execution exceeds timeout
    """
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        try:
            return future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"Execution exceeded timeout of {timeout_seconds}s")


def with_retry(
    func: Callable[..., T],
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 10.0,
    retry_on: tuple[type[Exception], ...] = (TimeoutError, RateLimitError),
) -> T:
    """Execute a function with exponential backoff retry.

    Args:
        func: Function to execute
        max_attempts: Maximum number of attempts
        min_wait: Initial wait time in seconds
        max_wait: Maximum wait time in seconds
        retry_on: Exception types that trigger retry

    Returns:
        Result of func

    Raises:
        RetryError: If all attempts fail
    """
    decorator = retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(retry_on),
        reraise=True,
        before_sleep=lambda retry_state: logger.warning(
            f"Retry attempt {retry_state.attempt_number} after error: "
            f"{retry_state.outcome.exception()}"
        ),
    )
    return decorator(func)()
