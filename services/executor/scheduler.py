"""Scheduling logic for cron and trigger mode execution."""

import logging
from datetime import datetime, timedelta

import redis.asyncio as redis
from croniter import croniter

logger = logging.getLogger(__name__)


def should_run_now(cron_expr: str, now: datetime) -> bool:
    """Check if a cron expression matches the current time.

    Args:
        cron_expr: Cron expression string (e.g., "0 9 * * MON")
        now: Current datetime

    Returns:
        True if the cron schedule should run now (within 1 minute window)
    """
    cron = croniter(cron_expr, now - timedelta(minutes=1))
    next_run = cron.get_next(datetime)

    # Within 1 minute window
    return abs((next_run - now).total_seconds()) < 60


async def load_all_schedules(redis_client: redis.Redis) -> dict[str, str]:
    """Load all experiment schedules from Redis.

    Args:
        redis_client: Redis client instance

    Returns:
        Dictionary mapping experiment IDs to cron expressions
    """
    schedules: dict[str, str] = {}

    async for key in redis_client.scan_iter("schedules:*"):
        # key is bytes or str depending on decode_responses
        key_str = key if isinstance(key, str) else key.decode()
        exp_id = key_str.split(":")[-1]
        cron_expr = await redis_client.get(key_str)

        if cron_expr is None:
            continue

        # Only include ready experiments
        state = await redis_client.hget(f"experiments:{exp_id}", "state")
        if state == "ready":
            schedules[exp_id] = cron_expr if isinstance(cron_expr, str) else cron_expr.decode()
            logger.debug(f"Loaded schedule for {exp_id}: {schedules[exp_id]}")

    logger.info(f"Loaded {len(schedules)} active schedules")
    return schedules


async def get_ready_experiments(redis_client: redis.Redis) -> list[dict]:
    """Get all experiments in 'ready' state for speedrun mode.

    Args:
        redis_client: Redis client instance

    Returns:
        List of experiment dictionaries
    """
    experiments = []

    async for key in redis_client.scan_iter("experiments:*"):
        key_str = key if isinstance(key, str) else key.decode()
        exp_id = key_str.split(":")[-1]

        state = await redis_client.hget(key_str, "state")
        if state == "ready":
            exp_data = await redis_client.hgetall(key_str)
            if exp_data:
                exp_data["id"] = exp_id
                experiments.append(exp_data)

    logger.info(f"Found {len(experiments)} ready experiments")
    return experiments


async def get_experiment(redis_client: redis.Redis, exp_id: str) -> dict | None:
    """Get a single experiment by ID.

    Args:
        redis_client: Redis client instance
        exp_id: Experiment ID

    Returns:
        Experiment dictionary or None if not found
    """
    exp_data = await redis_client.hgetall(f"experiments:{exp_id}")
    if exp_data:
        exp_data["id"] = exp_id
        return exp_data
    return None
