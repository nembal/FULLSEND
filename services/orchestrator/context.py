"""Context management for Orchestrator - reads/writes worklist.md and learnings.md."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiofiles
import redis.asyncio as redis

from .config import Settings

logger = logging.getLogger(__name__)


@dataclass
class Context:
    """All context needed for Orchestrator decision making."""

    product: str  # From product_context.md
    worklist: str  # From worklist.md
    learnings: str  # From learnings.md
    active_experiments: list[dict[str, Any]]
    available_tools: list[str]
    recent_metrics: dict[str, Any]


async def read_file_safe(path: Path) -> str:
    """Read a file with safe fallback if it doesn't exist."""
    try:
        async with aiofiles.open(path, mode="r") as f:
            return await f.read()
    except FileNotFoundError:
        logger.warning(f"Context file not found: {path}")
        return ""
    except Exception as e:
        logger.error(f"Error reading context file {path}: {e}")
        return ""


async def write_file(path: Path, content: str) -> None:
    """Write content to a file, creating parent directories if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(path, mode="w") as f:
        await f.write(content)


async def get_active_experiments(redis_client: redis.Redis) -> list[dict[str, Any]]:
    """Fetch active experiments from Redis.

    Scans for keys matching experiments:* and returns all non-archived experiments.
    Each experiment is stored as a Redis Hash with fields like:
    - id, hypothesis, state, created_at, etc.
    """
    experiments: list[dict[str, Any]] = []
    try:
        # Scan for all experiment keys
        cursor = 0
        while True:
            cursor, keys = await redis_client.scan(cursor, match="experiments:*", count=100)
            for key in keys:
                try:
                    exp_data = await redis_client.hgetall(key)
                    if exp_data:
                        # Decode bytes to strings if needed
                        decoded = {
                            k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
                            for k, v in exp_data.items()
                        }
                        # Only include non-archived experiments
                        if decoded.get("state") != "archived":
                            experiments.append(decoded)
                except Exception as e:
                    logger.warning(f"Error reading experiment key {key}: {e}")
            if cursor == 0:
                break
    except Exception as e:
        logger.error(f"Error scanning experiments from Redis: {e}")
    return experiments


async def get_available_tools(redis_client: redis.Redis) -> list[str]:
    """Fetch available tools from Redis registry.

    Scans for keys matching tools:* and returns names of active tools.
    Each tool is stored as a Redis Hash with fields like:
    - name, description, state, location, etc.
    """
    tools: list[str] = []
    try:
        cursor = 0
        while True:
            cursor, keys = await redis_client.scan(cursor, match="tools:*", count=100)
            for key in keys:
                try:
                    tool_data = await redis_client.hgetall(key)
                    if tool_data:
                        # Decode bytes to strings if needed
                        decoded = {
                            k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
                            for k, v in tool_data.items()
                        }
                        # Only include active tools
                        state = decoded.get("state", "active")
                        if state == "active":
                            name = decoded.get("name")
                            if name:
                                tools.append(name)
                            else:
                                # Fallback: extract name from key (tools:name)
                                key_str = key.decode() if isinstance(key, bytes) else key
                                tools.append(key_str.split(":", 1)[1])
                except Exception as e:
                    logger.warning(f"Error reading tool key {key}: {e}")
            if cursor == 0:
                break
    except Exception as e:
        logger.error(f"Error scanning tools from Redis: {e}")
    return tools


async def get_recent_metrics(redis_client: redis.Redis) -> dict[str, Any]:
    """Fetch recent aggregated metrics from Redis.

    Scans for keys matching metrics_aggregated:* and returns the latest values.
    Metrics are stored as Redis TimeSeries, but we read the most recent value.
    Falls back to Hash read if TimeSeries commands fail (for simpler deployments).
    """
    metrics: dict[str, Any] = {}
    try:
        cursor = 0
        while True:
            cursor, keys = await redis_client.scan(cursor, match="metrics_aggregated:*", count=100)
            for key in keys:
                key_str = key.decode() if isinstance(key, bytes) else key
                # Extract experiment_id from key (metrics_aggregated:{exp_id})
                exp_id = key_str.split(":", 1)[1] if ":" in key_str else key_str
                try:
                    # Try TimeSeries GET (returns most recent value)
                    # This requires Redis TimeSeries module
                    try:
                        # TS.GET returns (timestamp, value) tuple
                        result = await redis_client.execute_command("TS.GET", key)
                        if result:
                            timestamp, value = result
                            metrics[exp_id] = {
                                "timestamp": timestamp,
                                "value": float(value) if value is not None else None,
                            }
                    except Exception:
                        # Fallback: treat as a Hash for simpler setups
                        metric_data = await redis_client.hgetall(key)
                        if metric_data:
                            decoded = {
                                k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
                                for k, v in metric_data.items()
                            }
                            metrics[exp_id] = decoded
                except Exception as e:
                    logger.warning(f"Error reading metrics key {key_str}: {e}")
            if cursor == 0:
                break
    except Exception as e:
        logger.error(f"Error scanning metrics from Redis: {e}")
    return metrics


async def load_context(redis_client: redis.Redis, settings: Settings) -> Context:
    """Load all context needed for decision making."""
    context_path = settings.context_path

    # Read markdown files
    product = await read_file_safe(context_path / "product_context.md")
    worklist = await read_file_safe(context_path / "worklist.md")
    learnings = await read_file_safe(context_path / "learnings.md")

    # Read from Redis
    experiments = await get_active_experiments(redis_client)
    tools = await get_available_tools(redis_client)
    metrics = await get_recent_metrics(redis_client)

    return Context(
        product=product,
        worklist=worklist,
        learnings=learnings,
        active_experiments=experiments,
        available_tools=tools,
        recent_metrics=metrics,
    )


async def load_context_safe(redis_client: redis.Redis, settings: Settings) -> Context:
    """Load context with safe fallback on any error.

    This is the recommended entry point for loading context. It wraps load_context
    with a try/except to ensure the Orchestrator can always proceed with a decision,
    even if context loading fails partially or completely.

    Per PRD: Context file errors should not crash the service.

    Args:
        redis_client: Async Redis client for fetching experiments/tools/metrics
        settings: Orchestrator settings with context path

    Returns:
        Context with all available data, or empty Context on complete failure
    """
    try:
        return await load_context(redis_client, settings)
    except FileNotFoundError as e:
        logger.warning(f"Context file missing: {e}")
        return Context(
            product="",
            worklist="",
            learnings="",
            active_experiments=[],
            available_tools=[],
            recent_metrics={},
        )
    except Exception as e:
        logger.error(f"Error loading context: {e}", exc_info=True)
        return Context(
            product="",
            worklist="",
            learnings="",
            active_experiments=[],
            available_tools=[],
            recent_metrics={},
        )


async def update_worklist(new_content: str, settings: Settings) -> None:
    """Update worklist.md with new priorities."""
    path = settings.context_path / "worklist.md"
    await write_file(path, new_content)
    logger.info("Updated worklist.md")


async def append_learning(learning: str, settings: Settings) -> None:
    """Append a new learning to learnings.md."""
    path = settings.context_path / "learnings.md"
    current = await read_file_safe(path)
    timestamp = datetime.now(UTC).isoformat()
    updated = current + f"\n\n## {timestamp}\n{learning}"
    await write_file(path, updated)
    logger.info("Appended new learning to learnings.md")
