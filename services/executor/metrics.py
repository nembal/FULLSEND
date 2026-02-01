"""Metrics emission for experiment execution.

Includes:
- Metrics emission to Redis channels and lists
- Tool execution with timeout and retry logic
- Partial result handling on failures
"""

import asyncio
import json
import logging
import random
import time
from typing import Any, Callable

import redis.asyncio as redis

from .config import Settings
from .loader import ToolRetryExhaustedError, ToolTimeoutError

logger = logging.getLogger(__name__)

# Transient errors that should trigger retry
TRANSIENT_ERRORS = (
    ConnectionError,
    TimeoutError,
    OSError,
    IOError,
)


async def emit_metric(
    redis_client: redis.Redis,
    exp_id: str,
    metric: dict[str, Any],
    channel: str,
) -> None:
    """Emit a metric to the metrics stream.

    Args:
        redis_client: Redis client instance
        exp_id: Experiment ID
        metric: Metric data to emit
        channel: Redis channel to publish to
    """
    metric["experiment_id"] = exp_id

    # Publish to stream for Redis Agent
    await redis_client.publish(channel, json.dumps(metric))

    # Also append to experiment's metrics list
    await redis_client.rpush(f"metrics:{exp_id}", json.dumps(metric))

    logger.debug(f"Emitted metric: {metric.get('event')} for {exp_id}")


async def execute_with_timeout(
    fn: Callable[[], Any],
    timeout: int,
) -> Any:
    """Execute a function with timeout.

    Args:
        fn: Function to execute
        timeout: Timeout in seconds

    Returns:
        Result from the executed function

    Raises:
        ToolTimeoutError: If execution exceeds timeout
    """
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(fn),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        raise ToolTimeoutError(f"Tool execution exceeded {timeout}s timeout")


async def execute_with_retry(
    fn: Callable[[], Any],
    timeout: int,
    max_attempts: int,
    backoff_min: float,
    backoff_max: float,
) -> Any:
    """Execute a function with retry logic for transient failures.

    Uses exponential backoff with jitter for retry delays.

    Args:
        fn: Function to execute
        timeout: Timeout per attempt in seconds
        max_attempts: Maximum number of retry attempts
        backoff_min: Minimum backoff delay in seconds
        backoff_max: Maximum backoff delay in seconds

    Returns:
        Result from the executed function

    Raises:
        ToolTimeoutError: If execution exceeds timeout (not retried)
        ToolRetryExhaustedError: If all retry attempts fail
        Exception: For non-transient errors (not retried)
    """
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return await execute_with_timeout(fn, timeout)

        except ToolTimeoutError:
            # Timeouts are not retried - the tool is too slow
            raise

        except TRANSIENT_ERRORS as e:
            last_error = e
            logger.warning(
                f"Transient error on attempt {attempt}/{max_attempts}: {type(e).__name__}: {e}"
            )

            if attempt < max_attempts:
                # Calculate exponential backoff with jitter
                delay = min(backoff_min * (2 ** (attempt - 1)), backoff_max)
                delay = delay * (0.5 + random.random())  # Add jitter
                logger.info(f"Retrying in {delay:.2f}s...")
                await asyncio.sleep(delay)
            else:
                raise ToolRetryExhaustedError(
                    f"All {max_attempts} retry attempts exhausted",
                    last_error=e,
                    attempts=max_attempts,
                )

        except Exception:
            # Non-transient errors are not retried
            raise

    # Should not reach here, but satisfy type checker
    raise ToolRetryExhaustedError(
        f"All {max_attempts} retry attempts exhausted",
        last_error=last_error or Exception("Unknown error"),
        attempts=max_attempts,
    )


async def run_with_metrics(
    redis_client: redis.Redis,
    exp_id: str,
    run_id: str,
    fn: Callable[[], Any],
    settings: Settings,
) -> Any:
    """Run a function with timeout, retry, and metrics emission.

    Args:
        redis_client: Redis client instance
        exp_id: Experiment ID
        run_id: Run ID
        fn: Function to execute
        settings: Settings instance

    Returns:
        Result from the executed function

    Raises:
        ToolTimeoutError: If execution exceeds timeout
        ToolRetryExhaustedError: If all retry attempts fail for transient errors
        Exception: For non-transient errors
    """
    channel = settings.channel_metrics

    # Emit start metric
    await emit_metric(
        redis_client,
        exp_id,
        {
            "event": "run_started",
            "run_id": run_id,
            "timestamp": time.time(),
        },
        channel,
    )

    # Execute with timeout and retry
    result = await execute_with_retry(
        fn,
        timeout=settings.tool_execution_timeout,
        max_attempts=settings.retry_max_attempts,
        backoff_min=settings.retry_backoff_min,
        backoff_max=settings.retry_backoff_max,
    )

    # If result is iterable (e.g., list of emails sent), emit progress
    if hasattr(result, "__iter__") and not isinstance(result, (str, dict)):
        result = list(result)  # Materialize

        await emit_metric(
            redis_client,
            exp_id,
            {
                "event": "items_processed",
                "count": len(result),
                "run_id": run_id,
            },
            channel,
        )

    # Emit completion metric
    await emit_metric(
        redis_client,
        exp_id,
        {
            "event": "run_completed",
            "run_id": run_id,
            "timestamp": time.time(),
        },
        channel,
    )

    return result
