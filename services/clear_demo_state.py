"""
Clear Redis and RabbitMQ for a fresh demo run. Removes task state, tools, skills,
and purges all fullsend queues so the demo starts with no leftover messages.
"""

import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_TOOLS_KEY = os.getenv("REDIS_TOOLS_KEY", "tools:available")
REDIS_TASK_PREFIX = "task:"
REDIS_SKILLS_INDEX = "skills:index"
REDIS_SKILL_PREFIX = "skill:"
REDIS_CAMPAIGN_ACTIVE = "campaign:active"

# All fullsend queues (declare then purge)
DEMO_QUEUES = [
    "fullsend.orchestrator.tasks",
    "fullsend.worker.steps",
    "fullsend.worker.results.worked",
    "fullsend.worker.results.failed",
    "fullsend.builder.tasks",
    "fullsend.human.todo",
]


def clear_redis(redis_url: str | None = None) -> int:
    """
    Delete demo-related keys from Redis: tools:available, skills:index, skill:*, task:*.
    Returns number of keys deleted.
    """
    url = redis_url or REDIS_URL
    try:
        import redis
    except ImportError:
        logger.warning("redis not installed; skipping Redis clear")
        return 0
    try:
        r = redis.from_url(url, decode_responses=True)
        r.ping()
    except Exception as e:
        logger.warning("Redis connection failed: %s", e)
        return 0
    deleted = 0
    # Single keys
    for key in [REDIS_TOOLS_KEY, REDIS_SKILLS_INDEX, REDIS_CAMPAIGN_ACTIVE]:
        if r.delete(key):
            deleted += 1
            logger.debug("Deleted Redis key: %s", key)
    # Pattern keys
    for pattern in [f"{REDIS_TASK_PREFIX}*", f"{REDIS_SKILL_PREFIX}*"]:
        keys = r.keys(pattern)
        if keys:
            deleted += r.delete(*keys)
            logger.debug("Deleted %d Redis key(s) matching %s", len(keys), pattern)
    logger.info("Cleared Redis: %d key(s) deleted", deleted)
    return deleted


def clear_rabbitmq_queues(rabbitmq_url: str | None = None, queue_names: list[str] | None = None) -> int:
    """
    Declare and purge the given queues (default: DEMO_QUEUES). Returns number of queues purged.
    """
    url = rabbitmq_url or os.getenv("RABBITMQ_URL", "amqp://localhost:5672/")
    queues = queue_names or DEMO_QUEUES
    try:
        import pika
    except ImportError:
        logger.warning("pika not installed; skipping RabbitMQ clear")
        return 0
    try:
        params = pika.URLParameters(url)
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
    except Exception as e:
        logger.warning("RabbitMQ connection failed: %s", e)
        return 0
    purged = 0
    for name in queues:
        try:
            channel.queue_declare(queue=name, durable=True)
            result = channel.queue_purge(queue=name)
            purged += 1
            logger.debug("Purged queue: %s (messages removed: %s)", name, result)
        except Exception as e:
            logger.debug("Could not purge %s: %s", name, e)
    connection.close()
    logger.info("Purged %d RabbitMQ queue(s)", purged)
    return purged


def clear_redis_and_queues(
    redis_url: str | None = None,
    rabbitmq_url: str | None = None,
) -> tuple[int, int]:
    """
    Clear Redis (demo keys) and purge RabbitMQ (fullsend queues). Returns (redis_keys_deleted, queues_purged).
    Call at the start of run_demo for a fresh run.
    """
    r = clear_redis(redis_url)
    q = clear_rabbitmq_queues(rabbitmq_url)
    return r, q
