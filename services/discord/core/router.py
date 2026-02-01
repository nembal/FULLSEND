"""Message router for coordinating Redis subscriptions across adapters.

The router subscribes to Redis channels and dispatches messages to registered
handlers from both the Discord and Web adapters. This centralizes the Redis
subscription logic and ensures both adapters receive messages.
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from .bus import RedisBus, CHANNEL_FROM_AGENT, CHANNEL_TO_AGENT, publish_to_agent
from .messages import AgentMessage, HumanMessage

logger = logging.getLogger(__name__)

# Type for message handlers
MessageHandler = Callable[[str], Awaitable[None]]


class MessageRouter:
    """Routes messages between Redis and adapters.

    The router handles:
    - Subscribing to the from_agent channel
    - Dispatching messages to all registered handlers
    - Publishing messages to the to_agent channel
    """

    def __init__(self, redis_bus: RedisBus | None = None) -> None:
        """Initialize the message router.

        Args:
            redis_bus: Redis bus for pub/sub. If None, runs in offline mode.
        """
        self._redis_bus = redis_bus
        self._handlers: list[MessageHandler] = []
        self._subscribed = False
        self._lock = asyncio.Lock()

    @property
    def redis_bus(self) -> RedisBus | None:
        """Get the Redis bus."""
        return self._redis_bus

    @redis_bus.setter
    def redis_bus(self, bus: RedisBus | None) -> None:
        """Set the Redis bus."""
        self._redis_bus = bus

    @property
    def is_connected(self) -> bool:
        """Check if connected to Redis."""
        return self._redis_bus is not None and self._redis_bus.is_connected

    def register_handler(self, handler: MessageHandler) -> None:
        """Register a handler for incoming messages.

        Args:
            handler: Async function to call with message data
        """
        if handler not in self._handlers:
            self._handlers.append(handler)
            logger.debug("Registered message handler: %s", handler.__name__)

    def unregister_handler(self, handler: MessageHandler) -> None:
        """Unregister a message handler.

        Args:
            handler: Handler to remove
        """
        if handler in self._handlers:
            self._handlers.remove(handler)
            logger.debug("Unregistered message handler: %s", handler.__name__)

    async def start(self) -> None:
        """Start the router and subscribe to Redis.

        This should be called once Redis is connected.
        """
        async with self._lock:
            if self._subscribed:
                logger.debug("Router already subscribed")
                return

            if not self.is_connected:
                logger.warning("Cannot start router: Redis not connected")
                return

            try:
                await self._redis_bus.subscribe(CHANNEL_FROM_AGENT, self._on_message)
                self._subscribed = True
                logger.info("Message router subscribed to %s", CHANNEL_FROM_AGENT)
            except Exception as e:
                logger.error("Failed to start message router: %s", e)

    async def stop(self) -> None:
        """Stop the router and unsubscribe from Redis."""
        async with self._lock:
            if not self._subscribed:
                return

            if self._redis_bus is not None:
                try:
                    await self._redis_bus.unsubscribe(CHANNEL_FROM_AGENT)
                except Exception as e:
                    logger.error("Error unsubscribing router: %s", e)

            self._subscribed = False
            logger.info("Message router stopped")

    async def _on_message(self, data: str) -> None:
        """Handle incoming message from Redis.

        Dispatches the message to all registered handlers.

        Args:
            data: JSON-encoded message string
        """
        logger.debug("Router received message: %s", data[:100] if len(data) > 100 else data)

        # Dispatch to all handlers concurrently
        tasks = [self._dispatch_to_handler(handler, data) for handler in self._handlers]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _dispatch_to_handler(self, handler: MessageHandler, data: str) -> None:
        """Dispatch message to a single handler with error handling.

        Args:
            handler: Handler function to call
            data: Message data
        """
        try:
            await handler(data)
        except Exception as e:
            logger.exception("Error in message handler %s: %s", handler.__name__, e)

    async def publish(self, message: AgentMessage | HumanMessage | dict[str, Any] | str) -> int:
        """Publish a message to the to_agent channel.

        Args:
            message: Message to publish

        Returns:
            Number of subscribers that received the message

        Raises:
            ConnectionError: If not connected to Redis
        """
        if not self.is_connected:
            logger.warning("Cannot publish: Redis not connected")
            return 0

        return await publish_to_agent(self._redis_bus, message)

    async def publish_raw(self, channel: str, message: str | dict[str, Any]) -> int:
        """Publish a raw message to any channel.

        Args:
            channel: Channel to publish to
            message: Message to publish

        Returns:
            Number of subscribers that received the message
        """
        if not self.is_connected:
            logger.warning("Cannot publish: Redis not connected")
            return 0

        return await self._redis_bus.publish(channel, message)
