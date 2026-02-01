"""Metrics monitoring and aggregation for Redis Agent.

Handles:
- Subscription to fullsend:metrics stream
- Processing individual metric events
- Aggregating metrics per experiment
- Threshold checking loop
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis

from .alerts import send_alert
from .config import get_settings

logger = logging.getLogger(__name__)

# Lazy settings getter for module-level usage
_settings = None

def _get_settings():
    global _settings
    if _settings is None:
        _settings = get_settings()
    return _settings


async def monitor_metrics_stream(redis: Redis) -> None:
    """Subscribe to metrics stream and process events."""
    pubsub = redis.pubsub()
    await pubsub.subscribe(_get_settings().metrics_channel)
    logger.info(f"Subscribed to {_get_settings().metrics_channel}")

    async for message in pubsub.listen():
        if message["type"] == "message":
            try:
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                metric = json.loads(data)
                await process_metric(redis, metric)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse metric message: {e}")
            except Exception as e:
                logger.error(f"Error processing metric: {e}")


async def process_metric(redis: Redis, metric: dict[str, Any]) -> None:
    """Process a single metric event.

    - Stores raw metric in metrics:{experiment_id} list
    - Updates aggregations in metrics_aggregated:{experiment_id}
    - Sends immediate alerts for error events
    """
    exp_id = metric.get("experiment_id")
    if not exp_id:
        logger.warning("Metric missing experiment_id, skipping")
        return

    # Store raw metric with timestamp
    metric_with_ts = {**metric, "received_at": datetime.now(UTC).isoformat()}
    await redis.rpush(f"metrics:{exp_id}", json.dumps(metric_with_ts))
    logger.debug(f"Stored metric for {exp_id}: {metric}")

    # Update aggregations
    await update_aggregations(redis, exp_id, metric)

    # Check for immediate alerts (error events)
    if metric.get("event") == "error":
        await send_alert(
            redis,
            {
                "type": "error",
                "experiment_id": exp_id,
                "message": metric.get("message", "Unknown error"),
                "severity": "high",
            },
        )


async def update_aggregations(redis: Redis, exp_id: str, metric: dict[str, Any]) -> None:
    """Update aggregated metrics for an experiment.

    Aggregation keys stored in metrics_aggregated:{experiment_id} hash:
    - event counts: {event_name}_count
    - numeric values: {metric_name}_sum, {metric_name}_count, {metric_name}_latest
    - timestamps: last_updated
    """
    agg_key = f"metrics_aggregated:{exp_id}"

    # Track event counts
    event = metric.get("event")
    if event:
        await redis.hincrby(agg_key, f"{event}_count", 1)
        logger.debug(f"Incremented {event}_count for {exp_id}")

    # Aggregate numeric values
    for key, value in metric.items():
        if key in ("experiment_id", "event", "timestamp", "message"):
            continue

        if isinstance(value, (int, float)):
            # Increment sum and count for averages
            await redis.hincrbyfloat(agg_key, f"{key}_sum", float(value))
            await redis.hincrby(agg_key, f"{key}_count", 1)
            # Store latest value
            await redis.hset(agg_key, f"{key}_latest", str(value))
            logger.debug(f"Updated aggregation {key} for {exp_id}: {value}")

    # Update timestamp
    await redis.hset(agg_key, "last_updated", datetime.now(UTC).isoformat())


async def get_current_metrics(redis: Redis, exp_id: str) -> dict[str, Any]:
    """Get current aggregated metrics for an experiment.

    Returns a dict with:
    - Event counts
    - Computed averages (sum/count)
    - Latest values
    """
    agg_key = f"metrics_aggregated:{exp_id}"
    raw_agg = await redis.hgetall(agg_key)

    if not raw_agg:
        return {}

    metrics: dict[str, Any] = {}
    sums: dict[str, float] = {}
    counts: dict[str, int] = {}

    for key, value in raw_agg.items():
        if isinstance(key, bytes):
            key = key.decode("utf-8")
        if isinstance(value, bytes):
            value = value.decode("utf-8")

        if key.endswith("_count"):
            base = key.rsplit("_count", 1)[0]
            if base.endswith("_"):
                # This is a count for averaging (e.g., response_rate_count)
                counts[base.rstrip("_")] = int(value)
            else:
                # This is an event count (e.g., email_sent_count)
                metrics[key] = int(value)
        elif key.endswith("_sum"):
            base = key.rsplit("_sum", 1)[0]
            sums[base] = float(value)
        elif key.endswith("_latest"):
            base = key.rsplit("_latest", 1)[0]
            metrics[f"{base}_latest"] = float(value)
        elif key == "last_updated":
            metrics["last_updated"] = value

    # Compute averages
    for name in sums:
        if name in counts and counts[name] > 0:
            metrics[f"{name}_avg"] = sums[name] / counts[name]
        metrics[name] = sums[name]  # Also store total sum as the metric value

    return metrics


async def get_active_experiments(redis: Redis) -> list[dict[str, Any]]:
    """Get all active experiments from Redis.

    Looks for experiments:{id} hashes where status is 'active' or 'running'.
    """
    experiments = []

    # Scan for experiment keys
    cursor = 0
    while True:
        cursor, keys = await redis.scan(cursor, match="experiments:*", count=100)
        for key in keys:
            if isinstance(key, bytes):
                key = key.decode("utf-8")

            # Get experiment data
            exp_data = await redis.hgetall(key)
            if not exp_data:
                continue

            # Decode and parse
            exp = {}
            for k, v in exp_data.items():
                if isinstance(k, bytes):
                    k = k.decode("utf-8")
                if isinstance(v, bytes):
                    v = v.decode("utf-8")

                # Try to parse JSON values
                if k in ("success_criteria", "failure_criteria", "target"):
                    try:
                        exp[k] = json.loads(v)
                    except json.JSONDecodeError:
                        exp[k] = v
                else:
                    exp[k] = v

            # Extract ID from key
            exp["id"] = key.split(":", 1)[1] if ":" in key else key

            # Include if active (or if no status, assume active for monitoring)
            status = exp.get("status", "active")
            if status in ("active", "running", ""):
                experiments.append(exp)

        if cursor == 0:
            break

    return experiments


async def get_metrics_spec(redis: Redis, exp_id: str) -> dict[str, Any]:
    """Get metrics specification for an experiment."""
    spec_key = f"metrics_specs:{exp_id}"
    raw_spec = await redis.hgetall(spec_key)

    if not raw_spec:
        return {}

    spec = {}
    for k, v in raw_spec.items():
        if isinstance(k, bytes):
            k = k.decode("utf-8")
        if isinstance(v, bytes):
            v = v.decode("utf-8")
        try:
            spec[k] = json.loads(v)
        except json.JSONDecodeError:
            spec[k] = v

    return spec


async def check_thresholds_loop(redis: Redis) -> None:
    """Periodically check all experiments for threshold crossings."""
    logger.info("Starting threshold checking loop")

    while True:
        try:
            experiments = await get_active_experiments(redis)
            logger.debug(f"Checking thresholds for {len(experiments)} experiments")

            for exp in experiments:
                await check_experiment_thresholds(redis, exp)

        except Exception as e:
            logger.error(f"Error in threshold check loop: {e}")

        await asyncio.sleep(_get_settings().threshold_check_interval_seconds)


async def check_experiment_thresholds(redis: Redis, exp: dict[str, Any]) -> None:
    """Check if an experiment has crossed success/failure thresholds."""
    exp_id = exp.get("id", "")
    if not exp_id:
        return

    current_metrics = await get_current_metrics(redis, exp_id)
    if not current_metrics:
        return

    # Check success criteria
    success_criteria = exp.get("success_criteria", [])
    if isinstance(success_criteria, str):
        success_criteria = [success_criteria]

    for criterion in success_criteria:
        if evaluate_criterion(criterion, current_metrics):
            await send_alert(
                redis,
                {
                    "type": "success_threshold",
                    "experiment_id": exp_id,
                    "criterion": criterion,
                    "current_value": current_metrics,
                    "message": f"Experiment {exp_id} hit success: {criterion}",
                },
            )

    # Check failure criteria
    failure_criteria = exp.get("failure_criteria", [])
    if isinstance(failure_criteria, str):
        failure_criteria = [failure_criteria]

    for criterion in failure_criteria:
        if evaluate_criterion(criterion, current_metrics):
            await send_alert(
                redis,
                {
                    "type": "failure_threshold",
                    "experiment_id": exp_id,
                    "criterion": criterion,
                    "current_value": current_metrics,
                    "message": f"Experiment {exp_id} hit failure: {criterion}",
                    "severity": "high",
                },
            )


def evaluate_criterion(criterion: str, metrics: dict[str, Any]) -> bool:
    """Evaluate a criterion like 'response_rate > 0.10'.

    Supports operators: >, <, >=, <=, ==, !=
    """
    if not criterion or not isinstance(criterion, str):
        return False

    parts = criterion.split()
    if len(parts) != 3:
        logger.warning(f"Invalid criterion format: {criterion}")
        return False

    metric_name, operator, threshold_str = parts

    try:
        threshold = float(threshold_str)
    except ValueError:
        logger.warning(f"Invalid threshold value in criterion: {criterion}")
        return False

    # Look for the metric value - check both direct and _latest suffix
    value = metrics.get(metric_name)
    if value is None:
        value = metrics.get(f"{metric_name}_latest")
    if value is None:
        value = metrics.get(f"{metric_name}_avg")
    if value is None:
        return False

    try:
        value = float(value)
    except (ValueError, TypeError):
        return False

    if operator == ">":
        return value > threshold
    elif operator == "<":
        return value < threshold
    elif operator == ">=":
        return value >= threshold
    elif operator == "<=":
        return value <= threshold
    elif operator == "==":
        return value == threshold
    elif operator == "!=":
        return value != threshold

    logger.warning(f"Unknown operator in criterion: {operator}")
    return False
