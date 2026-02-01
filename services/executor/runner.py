"""Experiment execution logic."""

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as redis

from .config import Settings
from .loader import ToolError, ToolNotFoundError, ToolRetryExhaustedError, ToolTimeoutError, load_tool
from .metrics import run_with_metrics

logger = logging.getLogger(__name__)


def summarize_result(result: Any) -> dict[str, Any]:
    """Summarize execution result for storage.

    Args:
        result: Raw result from tool execution

    Returns:
        Summarized result dictionary
    """
    if isinstance(result, dict):
        return result
    if isinstance(result, list):
        return {"items": len(result), "type": "list"}
    return {"value": str(result)[:500]}


async def save_run_result(
    redis_client: redis.Redis,
    run_id: str,
    result: dict[str, Any],
) -> None:
    """Save run result to Redis.

    Args:
        redis_client: Redis client instance
        run_id: Run ID (format: {exp_id}:{timestamp})
        result: Result data to save
    """
    await redis_client.hset(f"experiment_runs:{run_id}", mapping=result)
    logger.debug(f"Saved run result: {run_id}")


async def publish_result(
    redis_client: redis.Redis,
    result: dict[str, Any],
    channel: str,
) -> None:
    """Publish execution result to Redis channel.

    Args:
        redis_client: Redis client instance
        result: Result data to publish
        channel: Redis channel to publish to
    """
    await redis_client.publish(channel, json.dumps(result))
    logger.debug(f"Published result to {channel}: {result.get('type')}")


async def execute_experiment(
    redis_client: redis.Redis,
    experiment: dict[str, Any],
    settings: Settings,
) -> None:
    """Execute a single experiment run.

    Args:
        redis_client: Redis client instance
        experiment: Experiment definition from Redis
        settings: Settings instance
    """
    exp_id = experiment["id"]
    run_id = f"{exp_id}:{int(time.time())}"

    logger.info(f"Starting experiment run: {run_id}")

    # Update experiment state
    await redis_client.hset(f"experiments:{exp_id}", "state", "running")

    try:
        # Get tool name from experiment execution config
        # Experiment data may be stored as JSON string or as hash fields
        execution = experiment.get("execution")
        if isinstance(execution, str):
            execution = json.loads(execution)
        elif execution is None:
            # Try getting tool directly from hash
            tool_name = experiment.get("tool")
            params = {}
            if experiment.get("params"):
                params = json.loads(experiment["params"]) if isinstance(experiment["params"], str) else experiment["params"]
            execution = {"tool": tool_name, "params": params}

        tool_name = execution["tool"]
        params = execution.get("params", {})

        logger.info(f"Loading tool: {tool_name}")

        # Load the required tool
        tool_fn = load_tool(tool_name, settings.tools_path)

        # Execute with metrics collection
        start_time = time.time()

        result = await run_with_metrics(
            redis_client,
            exp_id,
            run_id,
            lambda: tool_fn(**params),
            settings,
        )

        duration = time.time() - start_time

        # Save run results
        await save_run_result(
            redis_client,
            run_id,
            {
                "status": "completed",
                "duration_seconds": str(duration),
                "result_summary": json.dumps(summarize_result(result)),
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

        # Update experiment state
        await redis_client.hset(f"experiments:{exp_id}", "state", "run")

        # Notify completion
        await publish_result(
            redis_client,
            {
                "type": "experiment_completed",
                "experiment_id": exp_id,
                "run_id": run_id,
                "status": "success",
                "duration": duration,
            },
            settings.channel_experiment_results,
        )

        logger.info(f"Experiment completed: {run_id} in {duration:.2f}s")

    except ToolNotFoundError as e:
        logger.error(f"Tool not found: {e}")
        await _handle_failure(redis_client, exp_id, run_id, e, settings)

    except ToolTimeoutError as e:
        logger.error(f"Tool timeout: {e}")
        await _handle_failure(redis_client, exp_id, run_id, e, settings, is_timeout=True)

    except ToolRetryExhaustedError as e:
        logger.error(f"Retry exhausted: {e}")
        await _handle_failure(
            redis_client, exp_id, run_id, e, settings,
            retry_attempts=e.attempts,
            last_error=e.last_error,
        )

    except ToolError as e:
        logger.error(f"Tool error: {e}")
        await _handle_failure(redis_client, exp_id, run_id, e, settings)

    except Exception as e:
        logger.error(f"Experiment failed: {e}")
        await _handle_failure(redis_client, exp_id, run_id, e, settings)


async def _handle_failure(
    redis_client: redis.Redis,
    exp_id: str,
    run_id: str,
    error: Exception,
    settings: Settings,
    *,
    is_timeout: bool = False,
    retry_attempts: int | None = None,
    last_error: Exception | None = None,
) -> None:
    """Handle experiment execution failure.

    Args:
        redis_client: Redis client instance
        exp_id: Experiment ID
        run_id: Run ID
        error: Exception that caused failure
        settings: Settings instance
        is_timeout: Whether the failure was due to timeout
        retry_attempts: Number of retry attempts made (if applicable)
        last_error: The last underlying error (for retry exhaustion)
    """
    # Build failure details
    failure_data: dict[str, Any] = {
        "status": "failed",
        "error": str(error),
        "error_type": type(error).__name__,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    # Add timeout-specific details
    if is_timeout:
        failure_data["timeout_seconds"] = settings.tool_execution_timeout

    # Add retry-specific details
    if retry_attempts is not None:
        failure_data["retry_attempts"] = retry_attempts
        if last_error is not None:
            failure_data["last_transient_error"] = str(last_error)
            failure_data["last_transient_error_type"] = type(last_error).__name__

    # Save failure
    await save_run_result(redis_client, run_id, failure_data)

    # Update experiment state
    await redis_client.hset(f"experiments:{exp_id}", "state", "failed")

    # Build notification with additional details
    notification: dict[str, Any] = {
        "type": "experiment_failed",
        "experiment_id": exp_id,
        "run_id": run_id,
        "error": str(error),
        "error_type": type(error).__name__,
    }

    if is_timeout:
        notification["timeout_seconds"] = settings.tool_execution_timeout

    if retry_attempts is not None:
        notification["retry_attempts"] = retry_attempts

    # Notify failure
    await publish_result(
        redis_client,
        notification,
        settings.channel_experiment_results,
    )

    logger.error(f"Experiment failed: {run_id} - {error}")
