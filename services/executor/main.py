"""Main entry point for Executor service - scheduler and worker loop.

This module implements three schedule modes for experiment execution:

1. TRIGGER MODE (default):
   - Waits for explicit execution requests on `fullsend:execute_now`
   - Also listens for schedule updates on `fullsend:schedules`
   - Use: `SCHEDULE_MODE=trigger python -m services.executor.main`

2. CRON MODE:
   - Respects cron schedules in `schedules:{experiment_id}` Redis keys
   - Checks every `CRON_CHECK_INTERVAL` seconds (default: 60)
   - Use: `SCHEDULE_MODE=cron python -m services.executor.main`

3. SPEEDRUN MODE:
   - Runs ready experiments continuously for demos/testing
   - Runs every `SPEEDRUN_INTERVAL` seconds (default: 5)
   - Use: `SCHEDULE_MODE=speedrun python -m services.executor.main`
"""

import asyncio
import json
import logging
from datetime import UTC, datetime

import redis.asyncio as redis

from .config import Settings, get_settings
from .runner import execute_experiment
from .scheduler import get_experiment, get_ready_experiments, load_all_schedules, should_run_now

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run_speedrun_loop(redis_client: redis.Redis, settings: Settings) -> None:
    """Demo mode: run experiments continuously.

    Speedrun mode is designed for demos and development. It continuously
    fetches ready experiments and executes them in a tight loop.

    Configuration:
        - SPEEDRUN_INTERVAL: Seconds between cycles (default: 5)
        - SPEEDRUN_MAX_PER_CYCLE: Max experiments per cycle (default: 3)

    Args:
        redis_client: Redis client instance
        settings: Settings instance
    """
    logger.info(
        f"Speedrun mode: interval={settings.speedrun_interval}s, "
        f"max_per_cycle={settings.speedrun_max_per_cycle}"
    )

    cycle_count = 0
    while True:
        cycle_count += 1
        # Get all ready experiments
        experiments = await get_ready_experiments(redis_client)

        if experiments:
            logger.info(f"Cycle {cycle_count}: Found {len(experiments)} ready experiments")
            # Run up to max_per_cycle experiments
            for exp in experiments[: settings.speedrun_max_per_cycle]:
                await execute_experiment(redis_client, exp, settings)
        else:
            logger.debug(f"Cycle {cycle_count}: No ready experiments")

        await asyncio.sleep(settings.speedrun_interval)


async def run_cron_scheduler(redis_client: redis.Redis, settings: Settings) -> None:
    """Production mode: respect cron schedules.

    Cron mode checks Redis for experiment schedules and executes experiments
    when their cron expression matches the current time (within a 1-minute window).

    Schedules are stored as:
        - Key: `schedules:{experiment_id}`
        - Value: Cron expression (e.g., "0 9 * * MON")

    Configuration:
        - CRON_CHECK_INTERVAL: Seconds between checks (default: 60)

    Args:
        redis_client: Redis client instance
        settings: Settings instance
    """
    logger.info(f"Cron mode: check_interval={settings.cron_check_interval}s")
    schedules = await load_all_schedules(redis_client)
    logger.info(f"Loaded {len(schedules)} initial schedules")

    while True:
        now = datetime.now(UTC)
        executed_count = 0

        for exp_id, cron_expr in schedules.items():
            if should_run_now(cron_expr, now):
                logger.info(f"Cron triggered: {exp_id} (schedule: {cron_expr})")
                exp = await get_experiment(redis_client, exp_id)
                if exp:
                    await execute_experiment(redis_client, exp, settings)
                    executed_count += 1

        if executed_count:
            logger.info(f"Cron cycle: executed {executed_count} experiments")

        # Reload schedules to pick up any updates
        schedules = await load_all_schedules(redis_client)

        await asyncio.sleep(settings.cron_check_interval)


async def run_trigger_mode(redis_client: redis.Redis, settings: Settings) -> None:
    """Wait for explicit trigger via Redis channel.

    Trigger mode subscribes to two channels:
        1. `fullsend:execute_now` - Execute experiment immediately
           Message format: {"experiment_id": "exp_123"}

        2. `fullsend:schedules` - Schedule updates (for logging/awareness)
           Message format: {"experiment_id": "exp_123", "schedule": "0 9 * * MON"}

    This is the default mode, suitable for production environments where
    an external orchestrator controls when experiments run.

    Args:
        redis_client: Redis client instance
        settings: Settings instance
    """
    logger.info(
        f"Trigger mode: listening on [{settings.channel_execute_now}, {settings.channel_schedules}]"
    )
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(settings.channel_execute_now, settings.channel_schedules)

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue

        channel = message.get("channel", "")
        if isinstance(channel, bytes):
            channel = channel.decode()

        try:
            data = json.loads(message["data"])

            if channel == settings.channel_execute_now:
                # Execute experiment immediately
                exp_id = data.get("experiment_id")
                if exp_id:
                    logger.info(f"Trigger received: executing {exp_id}")
                    exp = await get_experiment(redis_client, exp_id)
                    if exp:
                        await execute_experiment(redis_client, exp, settings)
                    else:
                        logger.warning(f"Experiment not found: {exp_id}")
                else:
                    logger.warning("Trigger message missing experiment_id")

            elif channel == settings.channel_schedules:
                # Log schedule update (cron mode would act on this)
                exp_id = data.get("experiment_id")
                schedule = data.get("schedule")
                logger.info(f"Schedule update received: {exp_id} -> {schedule}")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message: {e}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")


async def main() -> None:
    """Main entry point - start the executor in configured mode.

    The executor runs in one of three modes based on SCHEDULE_MODE env var:
        - trigger (default): Wait for Redis pub/sub messages
        - cron: Check Redis schedules on interval
        - speedrun: Run all ready experiments continuously
    """
    settings = get_settings()

    logger.info("=" * 60)
    logger.info("Starting Executor service")
    logger.info("=" * 60)
    logger.info(f"Mode: {settings.get_mode_description()}")
    logger.info(f"Redis: {settings.redis_url}")
    logger.info(f"Tools path: {settings.tools_path}")
    logger.info(f"Tool timeout: {settings.tool_execution_timeout}s")
    logger.info("=" * 60)

    # Connect to Redis
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)

    try:
        # Test connection
        await redis_client.ping()
        logger.info("Connected to Redis")

        if settings.schedule_mode == "speedrun":
            await run_speedrun_loop(redis_client, settings)
        elif settings.schedule_mode == "cron":
            await run_cron_scheduler(redis_client, settings)
        else:
            # Default: trigger mode
            await run_trigger_mode(redis_client, settings)

    except KeyboardInterrupt:
        logger.info("Shutting down Executor...")
    finally:
        await redis_client.aclose()
        logger.info("Executor stopped")


if __name__ == "__main__":
    asyncio.run(main())
