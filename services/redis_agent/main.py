"""Redis Agent main entry point.

Runs the metrics monitoring daemon with parallel tasks:
- monitor_metrics_stream: Subscribe to metrics and process events
- check_thresholds_loop: Periodically evaluate success/failure criteria
- run_periodic_summaries: Generate hourly LLM summaries
"""

import asyncio
import logging
import sys

from redis.asyncio import Redis

from .analyzer import run_periodic_summaries
from .config import get_settings
from .monitor import check_thresholds_loop, monitor_metrics_stream

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Main entry point for Redis Agent daemon."""
    settings = get_settings()

    logger.info("Starting Redis Agent")
    logger.info(f"Redis URL: {settings.redis_url}")
    logger.info(f"Metrics channel: {settings.metrics_channel}")
    logger.info(f"Alert cooldown: {settings.alert_cooldown_seconds}s")
    logger.info(f"Summary interval: {settings.summary_interval_seconds}s")

    # Connect to Redis
    redis = Redis.from_url(settings.redis_url)

    try:
        # Test connection
        await redis.ping()
        logger.info("Connected to Redis")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise

    try:
        # Start parallel tasks
        await asyncio.gather(
            monitor_metrics_stream(redis),
            check_thresholds_loop(redis),
            run_periodic_summaries(redis),
        )
    finally:
        await redis.close()
        logger.info("Redis Agent shutdown complete")


def run() -> None:
    """Entry point for running as a module."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Received interrupt, shutting down...")


if __name__ == "__main__":
    run()
