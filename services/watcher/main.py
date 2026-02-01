"""Main entry point for Watcher service - daemon loop for message processing."""

import asyncio
import json
import logging
from typing import Any

import redis.asyncio as redis

from .classifier import Classification, classify
from .config import get_settings
from .escalator import build_error_escalation, build_escalation, publish_escalation
from .responder import generate_response
from .retry import ModelCallError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def process_message(
    msg: dict[str, Any],
    redis_client: redis.Redis,
    settings: Any,
) -> None:
    """Process a single Discord message through classification and routing.

    Includes retry logic for model calls. On failure after all retries,
    escalates the message with error details.
    """
    logger.info(f"Processing message from {msg.get('username')}: {msg.get('content', '')[:50]}...")

    # 1. Classify the message (with retry logic)
    try:
        classification = await classify(msg, settings)
        logger.info(f"Classification: {classification.action} (priority: {classification.priority})")
    except ModelCallError as e:
        # Classification failed after all retries - escalate with error
        logger.error(f"Classification failed after retries: {e}")
        error_payload = build_error_escalation(
            msg,
            e.last_error,
            error_type=f"classification_failed_after_{e.attempts}_attempts",
        )
        await publish_escalation(error_payload, redis_client, settings.channel_to_orchestrator)
        logger.info("Escalated message due to classification failure")
        return

    # 2. Route based on classification
    if classification.action == "ignore":
        logger.debug(f"Ignoring message: {classification.reason}")
        return

    elif classification.action == "answer":
        try:
            response = await generate_response(msg, classification, redis_client, settings)
            payload = {
                "type": "watcher_response",
                "channel_id": msg.get("channel_id"),
                "reply_to": msg.get("message_id"),
                "content": response,
            }
            await redis_client.publish(settings.channel_from_orchestrator, json.dumps(payload))
            logger.info("Sent simple response to Discord")
        except ModelCallError as e:
            # Response generation failed after all retries - escalate with error
            logger.error(f"Response generation failed after retries: {e}")
            error_payload = build_error_escalation(
                msg,
                e.last_error,
                error_type=f"response_generation_failed_after_{e.attempts}_attempts",
            )
            await publish_escalation(error_payload, redis_client, settings.channel_to_orchestrator)
            logger.info("Escalated message due to response generation failure")

    elif classification.action == "escalate":
        payload = build_escalation(msg, classification)
        await publish_escalation(payload, redis_client, settings.channel_to_orchestrator)
        logger.info(f"Escalated to Orchestrator: {classification.reason}")


async def main() -> None:
    """Main daemon loop - subscribe to Discord messages and process them."""
    settings = get_settings()
    logger.info("Starting Watcher service...")
    logger.info(f"Model: {settings.watcher_model}")
    logger.info(f"Redis: {settings.redis_url}")

    # Connect to Redis
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    pubsub = redis_client.pubsub()

    try:
        await pubsub.subscribe(settings.channel_discord_raw)
        logger.info(f"Subscribed to {settings.channel_discord_raw}")

        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    await process_message(data, redis_client, settings)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse message: {e}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}")

    except KeyboardInterrupt:
        logger.info("Shutting down Watcher...")
    finally:
        await pubsub.unsubscribe(settings.channel_discord_raw)
        await redis_client.aclose()
        logger.info("Watcher stopped")


if __name__ == "__main__":
    asyncio.run(main())
