"""Redis pub/sub bus for inter-service communication.

Provides async pub/sub connection to Redis for message passing between
the Discord adapter, web adapter, and the orchestrator.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import redis.asyncio as redis
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Channel names for message routing
CHANNEL_TO_AGENT = "fullsend:to_agent"
CHANNEL_FROM_AGENT = "fullsend:from_agent"


class RedisBus:
    """Async Redis pub/sub wrapper for message bus communication."""

    def __init__(self, redis_url: str = "redis://localhost:6379") -> None:
        """Initialize the Redis bus.

        Args:
            redis_url: Redis connection URL
        """
        self._redis_url = redis_url
        self._redis: redis.Redis | None = None
        self._pubsub: redis.client.PubSub | None = None
        self._callbacks: dict[str, list[Callable[[str], Awaitable[None]]]] = {}
        self._listener_task: asyncio.Task | None = None
        self._running = False

    @property
    def is_connected(self) -> bool:
        """Check if connected to Redis."""
        return self._redis is not None and self._running

    async def connect(self) -> None:
        """Connect to Redis.

        Raises:
            ConnectionError: If unable to connect to Redis
        """
        if self._redis is not None:
            logger.warning("Already connected to Redis")
            return

        try:
            self._redis = redis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            # Test the connection
            await self._redis.ping()
            self._pubsub = self._redis.pubsub()
            self._running = True
            logger.info("Connected to Redis at %s", self._redis_url)
        except redis.ConnectionError as e:
            self._redis = None
            self._pubsub = None
            logger.error("Failed to connect to Redis: %s", e)
            raise ConnectionError(f"Failed to connect to Redis: {e}") from e

    async def disconnect(self) -> None:
        """Disconnect from Redis and clean up resources."""
        self._running = False

        if self._listener_task is not None:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

        if self._pubsub is not None:
            await self._pubsub.unsubscribe()
            await self._pubsub.close()
            self._pubsub = None

        if self._redis is not None:
            await self._redis.close()
            self._redis = None

        self._callbacks.clear()
        logger.info("Disconnected from Redis")

    async def publish(self, channel: str, message: str | BaseModel | dict[str, Any]) -> int:
        """Publish a message to a channel.

        Args:
            channel: Channel name to publish to
            message: Message to publish (string, Pydantic model, or dict)

        Returns:
            Number of subscribers that received the message

        Raises:
            ConnectionError: If not connected to Redis
        """
        if self._redis is None:
            raise ConnectionError("Not connected to Redis")

        # Convert message to string
        if isinstance(message, BaseModel):
            message_str = message.model_dump_json()
        elif isinstance(message, dict):
            import json
            message_str = json.dumps(message)
        else:
            message_str = str(message)

        try:
            result = await self._redis.publish(channel, message_str)
            logger.debug("Published message to %s: %s", channel, message_str[:100])
            return result
        except redis.ConnectionError as e:
            logger.error("Failed to publish message: %s", e)
            raise ConnectionError(f"Failed to publish message: {e}") from e

    async def subscribe(
        self,
        channel: str,
        callback: Callable[[str], Awaitable[None]],
    ) -> None:
        """Subscribe to a channel with a callback.

        Args:
            channel: Channel name to subscribe to
            callback: Async function to call when a message is received

        Raises:
            ConnectionError: If not connected to Redis
        """
        if self._pubsub is None:
            raise ConnectionError("Not connected to Redis")

        # Register callback
        if channel not in self._callbacks:
            self._callbacks[channel] = []
            await self._pubsub.subscribe(channel)
            logger.info("Subscribed to channel: %s", channel)

        self._callbacks[channel].append(callback)

        # Start listener if not already running
        if self._listener_task is None or self._listener_task.done():
            self._listener_task = asyncio.create_task(self._listen())

    async def unsubscribe(self, channel: str) -> None:
        """Unsubscribe from a channel.

        Args:
            channel: Channel name to unsubscribe from
        """
        if self._pubsub is None:
            return

        if channel in self._callbacks:
            del self._callbacks[channel]
            await self._pubsub.unsubscribe(channel)
            logger.info("Unsubscribed from channel: %s", channel)

    async def _listen(self) -> None:
        """Listen for messages and dispatch to callbacks."""
        if self._pubsub is None:
            return

        logger.info("Starting message listener")
        try:
            while self._running:
                try:
                    message = await self._pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1.0,
                    )
                    if message is not None and message["type"] == "message":
                        channel = message["channel"]
                        data = message["data"]
                        await self._dispatch(channel, data)
                except asyncio.CancelledError:
                    break
                except redis.ConnectionError as e:
                    logger.error("Connection error while listening: %s", e)
                    await asyncio.sleep(1.0)  # Wait before retry
        except Exception as e:
            logger.exception("Unexpected error in listener: %s", e)
        finally:
            logger.info("Message listener stopped")

    async def _dispatch(self, channel: str, data: str) -> None:
        """Dispatch a message to registered callbacks.

        Args:
            channel: Channel the message was received on
            data: Message data
        """
        callbacks = self._callbacks.get(channel, [])
        for callback in callbacks:
            try:
                await callback(data)
            except Exception as e:
                logger.exception("Error in callback for channel %s: %s", channel, e)


# Convenience functions for common channels
async def publish_to_agent(bus: RedisBus, message: str | BaseModel | dict[str, Any]) -> int:
    """Publish a message to the agent (orchestrator).

    Args:
        bus: RedisBus instance
        message: Message to send

    Returns:
        Number of subscribers that received the message
    """
    return await bus.publish(CHANNEL_TO_AGENT, message)


async def subscribe_from_agent(
    bus: RedisBus,
    callback: Callable[[str], Awaitable[None]],
) -> None:
    """Subscribe to messages from the agent (orchestrator).

    Args:
        bus: RedisBus instance
        callback: Async function to call when a message is received
    """
    await bus.subscribe(CHANNEL_FROM_AGENT, callback)
