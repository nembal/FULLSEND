#!/usr/bin/env python3
"""Round-trip test for Redis message flow.

This script tests that messages flow correctly:
1. Publish to to_agent channel (simulating adapter -> orchestrator)
2. Receive on from_agent channel (simulating orchestrator -> adapters)
3. Verify messages reach registered handlers

Usage:
    python -m services.discord.test_roundtrip

Requirements:
    - Redis running locally on localhost:6379
"""

import asyncio
import json
import logging
import sys
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def test_roundtrip() -> bool:
    """Test round-trip message flow through Redis.

    Returns:
        True if all tests pass, False otherwise.
    """
    from .core.bus import RedisBus, CHANNEL_TO_AGENT, CHANNEL_FROM_AGENT
    from .core.router import MessageRouter
    from .core.messages import AgentMessage, AgentMessageType, HumanMessage, HumanMessageType

    # Track received messages
    received_messages: list[str] = []
    received_event = asyncio.Event()

    async def handler1(data: str) -> None:
        """First handler - simulates Discord adapter."""
        logger.info("[Handler1/Discord] Received: %s", data[:100])
        received_messages.append(("handler1", data))
        received_event.set()

    async def handler2(data: str) -> None:
        """Second handler - simulates Web adapter."""
        logger.info("[Handler2/Web] Received: %s", data[:100])
        received_messages.append(("handler2", data))

    # Connect to Redis
    logger.info("Connecting to Redis...")
    bus = RedisBus("redis://localhost:6379")
    try:
        await bus.connect()
    except ConnectionError as e:
        logger.error("Failed to connect to Redis: %s", e)
        logger.error("Make sure Redis is running on localhost:6379")
        return False

    logger.info("Connected to Redis")

    # Create message router
    router = MessageRouter(bus)
    router.register_handler(handler1)
    router.register_handler(handler2)

    # Start router (subscribes to from_agent channel)
    await router.start()
    logger.info("Message router started")

    # Allow subscription to settle
    await asyncio.sleep(0.5)

    # --- Test 1: Publish to from_agent (simulating orchestrator) ---
    logger.info("\n=== Test 1: Orchestrator -> Adapters ===")
    test_message = AgentMessage(
        type=AgentMessageType.STATUS_UPDATE,
        payload={"status": "test", "message": "Round-trip test message"},
    )

    # Publish directly to from_agent channel to simulate orchestrator
    await bus.publish(CHANNEL_FROM_AGENT, test_message)
    logger.info("Published test message to %s", CHANNEL_FROM_AGENT)

    # Wait for message to be received
    try:
        await asyncio.wait_for(received_event.wait(), timeout=5.0)
    except asyncio.TimeoutError:
        logger.error("Timeout waiting for message - FAILED")
        await bus.disconnect()
        return False

    # Verify both handlers received the message
    if len(received_messages) != 2:
        logger.error("Expected 2 handlers to receive message, got %d - FAILED", len(received_messages))
        await bus.disconnect()
        return False

    logger.info("Both handlers received the message - PASSED")

    # --- Test 2: Publish to to_agent (simulating adapters) ---
    logger.info("\n=== Test 2: Adapters -> Orchestrator ===")
    received_from_adapter: list[str] = []
    adapter_event = asyncio.Event()

    async def orchestrator_handler(data: str) -> None:
        """Handler simulating orchestrator receiving messages."""
        logger.info("[Orchestrator] Received: %s", data[:100])
        received_from_adapter.append(data)
        adapter_event.set()

    # Subscribe to to_agent channel (simulating orchestrator)
    await bus.subscribe(CHANNEL_TO_AGENT, orchestrator_handler)
    await asyncio.sleep(0.5)

    # Publish via router (simulating adapter publishing)
    idea_message = HumanMessage(
        type=HumanMessageType.IDEA_SUBMIT,
        payload={"content": "Test idea from adapter"},
        source="test",
        user_id="test_user",
    )
    await router.publish(idea_message)
    logger.info("Published idea message to %s", CHANNEL_TO_AGENT)

    # Wait for orchestrator to receive
    try:
        await asyncio.wait_for(adapter_event.wait(), timeout=5.0)
    except asyncio.TimeoutError:
        logger.error("Timeout waiting for orchestrator message - FAILED")
        await bus.disconnect()
        return False

    # Verify orchestrator received the message
    if len(received_from_adapter) != 1:
        logger.error("Expected 1 message at orchestrator, got %d - FAILED", len(received_from_adapter))
        await bus.disconnect()
        return False

    # Verify content
    received_data = json.loads(received_from_adapter[0])
    if received_data.get("type") != "idea_submit":
        logger.error("Unexpected message type: %s - FAILED", received_data.get("type"))
        await bus.disconnect()
        return False

    logger.info("Orchestrator received adapter message - PASSED")

    # --- Test 3: Multiple message types ---
    logger.info("\n=== Test 3: Multiple message types ===")
    received_messages.clear()
    received_event.clear()

    message_types = [
        AgentMessageType.ACTION_REQUEST,
        AgentMessageType.IDEA_ACK,
        AgentMessageType.WIN_ALERT,
    ]

    for msg_type in message_types:
        msg = AgentMessage(
            type=msg_type,
            payload={"test_type": msg_type.value},
        )
        await bus.publish(CHANNEL_FROM_AGENT, msg)
        await asyncio.sleep(0.1)

    # Wait a bit for all messages
    await asyncio.sleep(1.0)

    # Each message should be received by 2 handlers = 6 total
    expected_count = len(message_types) * 2
    if len(received_messages) != expected_count:
        logger.error("Expected %d messages, got %d - FAILED", expected_count, len(received_messages))
        await bus.disconnect()
        return False

    logger.info("All message types received correctly - PASSED")

    # Cleanup
    await router.stop()
    await bus.disconnect()

    logger.info("\n=== All round-trip tests PASSED ===")
    return True


def main() -> None:
    """Main entry point."""
    logger.info("Starting round-trip message flow test")
    logger.info("=" * 60)

    success = asyncio.run(test_roundtrip())

    if success:
        logger.info("\nResult: SUCCESS")
        sys.exit(0)
    else:
        logger.error("\nResult: FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
