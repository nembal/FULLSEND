"""Retry logic for model API calls with exponential backoff."""

import asyncio
import logging
from functools import wraps
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ModelCallError(Exception):
    """Raised when a model call fails after all retries."""

    def __init__(self, message: str, attempts: int, last_error: Exception):
        self.message = message
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(f"{message} after {attempts} attempts: {last_error}")


async def retry_model_call(
    func: Callable[..., T],
    *args: Any,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    **kwargs: Any,
) -> T:
    """Execute a function with retry logic and exponential backoff.

    Args:
        func: The async or sync function to call
        *args: Positional arguments to pass to the function
        max_attempts: Maximum number of attempts (default 3)
        base_delay: Initial delay in seconds between retries (default 1.0)
        max_delay: Maximum delay in seconds between retries (default 10.0)
        **kwargs: Keyword arguments to pass to the function

    Returns:
        The result of the function call

    Raises:
        ModelCallError: If all retry attempts fail
    """
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        except Exception as e:
            last_error = e
            if attempt < max_attempts:
                delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                logger.warning(
                    f"Model call failed (attempt {attempt}/{max_attempts}): {e}. "
                    f"Retrying in {delay:.1f}s..."
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    f"Model call failed after {max_attempts} attempts: {e}"
                )

    raise ModelCallError(
        message="Model call failed",
        attempts=max_attempts,
        last_error=last_error,  # type: ignore
    )


def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator to add retry logic to an async function.

    Args:
        max_attempts: Maximum number of attempts (default 3)
        base_delay: Initial delay in seconds between retries (default 1.0)
        max_delay: Maximum delay in seconds between retries (default 10.0)

    Returns:
        Decorated function with retry logic
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await retry_model_call(
                func,
                *args,
                max_attempts=max_attempts,
                base_delay=base_delay,
                max_delay=max_delay,
                **kwargs,
            )

        return wrapper  # type: ignore

    return decorator
