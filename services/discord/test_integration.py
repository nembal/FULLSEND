#!/usr/bin/env python3
"""Integration test script for Fullsend Discord Communication Service.

This script tests the complete integration between:
1. Redis pub/sub message flow
2. Discord bot message handling
3. Web dashboard WebSocket updates

Prerequisites:
    - Redis running locally on localhost:6379
    - For Discord bot testing: Bot must be running with valid DISCORD_TOKEN
    - For web testing: Web adapter must be running on WEB_PORT (default 8000)

Usage:
    # Run automated Redis + Web API tests only (no Discord required):
    python -m services.discord.test_integration

    # Run with web adapter live (starts test server):
    python -m services.discord.test_integration --with-web

Manual Test Steps:
==================

1. REDIS MESSAGE FLOW TEST
   -----------------------
   a. Start Redis: `redis-server`
   b. Start the service: `python -m services.discord.main`
   c. Run this test script: `python -m services.discord.test_integration`
   d. Verify messages are published and received correctly

2. DISCORD BOT TEST (requires real Discord server)
   ------------------------------------------------
   a. Set up .env file with valid DISCORD_TOKEN and DISCORD_GUILD_ID
   b. Start Redis: `redis-server`
   c. Start the service: `ENV=discord python -m services.discord.main`
   d. In your Discord server:
      - Use /status to check bot is running
      - Use /pause to pause the bot
      - Use /go to resume the bot
      - Use /idea "test idea" to submit an idea
      - Post a message in a LISTENING_CHANNEL to trigger emoji reaction
   e. Run this script to send mock agent messages:
      `python -m services.discord.test_integration --send-mock`
   f. Verify STATUS_CHANNEL receives status_update, learning_share, win_alert posts

3. WEB DASHBOARD TEST
   -------------------
   a. Start Redis: `redis-server`
   b. Start the service: `ENV=web python -m services.discord.main`
   c. Open browser to http://localhost:8000
   d. Verify dashboard loads correctly
   e. Run this script to send mock messages:
      `python -m services.discord.test_integration --send-mock`
   f. Verify WebSocket messages appear in live feed
   g. Test controls:
      - Click "Go" button, verify status changes
      - Click "Pause" button, verify status changes
      - Submit an idea via the textarea

4. FULL INTEGRATION TEST (Discord + Web)
   --------------------------------------
   a. Set up .env with all required vars
   b. Start Redis: `redis-server`
   c. Start the service: `ENV=both python -m services.discord.main`
   d. Open web dashboard at http://localhost:8000
   e. Use Discord commands and verify web feed updates
   f. Use web controls and verify changes reflect
   g. Run this script to send mock agent messages and observe both adapters
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from typing import Any

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ============================================================================
# Mock Message Generators
# ============================================================================

def create_status_update(message: str) -> dict[str, Any]:
    """Create a mock status_update message."""
    return {
        "type": "status_update",
        "payload": {
            "status": "active",
            "message": message,
        },
        "timestamp": datetime.utcnow().isoformat(),
        "priority": "normal",
    }


def create_learning_share(insight: str) -> dict[str, Any]:
    """Create a mock learning_share message."""
    return {
        "type": "learning_share",
        "payload": {
            "insight": insight,
            "source": "integration_test",
        },
        "timestamp": datetime.utcnow().isoformat(),
        "priority": "normal",
    }


def create_win_alert(achievement: str) -> dict[str, Any]:
    """Create a mock win_alert message."""
    return {
        "type": "win_alert",
        "payload": {
            "achievement": achievement,
            "details": "Automated integration test",
        },
        "timestamp": datetime.utcnow().isoformat(),
        "priority": "high",
    }


def create_action_request(description: str, action_type: str = "manual_task") -> dict[str, Any]:
    """Create a mock action_request message."""
    import uuid
    return {
        "type": "action_request",
        "payload": {
            "id": str(uuid.uuid4()),
            "description": description,
            "action_type": action_type,
            "details": {"test": True, "source": "integration_test"},
            "assignee": None,
            "deadline": None,
        },
        "timestamp": datetime.utcnow().isoformat(),
        "priority": "normal",
    }


def create_idea_ack(content: str) -> dict[str, Any]:
    """Create a mock idea_ack message."""
    return {
        "type": "idea_ack",
        "payload": {
            "content": content,
            "status": "received",
        },
        "timestamp": datetime.utcnow().isoformat(),
        "priority": "normal",
    }


# ============================================================================
# Redis Tests
# ============================================================================

async def test_redis_connection() -> bool:
    """Test Redis connection."""
    from .core.bus import RedisBus

    logger.info("Testing Redis connection...")
    bus = RedisBus("redis://localhost:6379")

    try:
        await bus.connect()
        logger.info("✅ Redis connection successful")
        await bus.disconnect()
        return True
    except ConnectionError as e:
        logger.error(f"❌ Redis connection failed: {e}")
        logger.error("Make sure Redis is running on localhost:6379")
        return False


async def test_pubsub_roundtrip() -> bool:
    """Test Redis pub/sub message roundtrip."""
    from .core.bus import RedisBus, CHANNEL_FROM_AGENT, CHANNEL_TO_AGENT

    logger.info("Testing Redis pub/sub roundtrip...")

    bus = RedisBus("redis://localhost:6379")
    try:
        await bus.connect()
    except ConnectionError:
        logger.error("❌ Cannot connect to Redis for roundtrip test")
        return False

    received: list[str] = []
    event = asyncio.Event()

    async def handler(data: str) -> None:
        received.append(data)
        event.set()

    # Subscribe to from_agent channel
    await bus.subscribe(CHANNEL_FROM_AGENT, handler)
    await asyncio.sleep(0.3)

    # Publish test message
    test_msg = create_status_update("Integration test roundtrip")
    await bus.publish(CHANNEL_FROM_AGENT, test_msg)

    # Wait for message
    try:
        await asyncio.wait_for(event.wait(), timeout=5.0)
    except asyncio.TimeoutError:
        logger.error("❌ Timeout waiting for pub/sub message")
        await bus.disconnect()
        return False

    if received:
        logger.info("✅ Pub/sub roundtrip successful")
        await bus.disconnect()
        return True
    else:
        logger.error("❌ No message received")
        await bus.disconnect()
        return False


async def send_mock_agent_messages() -> bool:
    """Send mock agent messages to Redis (for manual testing with adapters)."""
    from .core.bus import RedisBus, CHANNEL_FROM_AGENT

    logger.info("Sending mock agent messages to Redis...")

    bus = RedisBus("redis://localhost:6379")
    try:
        await bus.connect()
    except ConnectionError:
        logger.error("❌ Cannot connect to Redis")
        return False

    messages = [
        ("status_update", create_status_update("Agent is processing your request...")),
        ("learning_share", create_learning_share("Discovered new pattern in user behavior")),
        ("win_alert", create_win_alert("Successfully completed 100 tasks!")),
        ("action_request", create_action_request("Review and approve the latest PR")),
        ("idea_ack", create_idea_ack("Great idea - adding to the backlog!")),
    ]

    for msg_type, msg in messages:
        await bus.publish(CHANNEL_FROM_AGENT, msg)
        logger.info(f"  Sent: {msg_type}")
        await asyncio.sleep(1.0)  # Rate limit between messages

    logger.info("✅ All mock messages sent")
    await bus.disconnect()
    return True


async def test_to_agent_channel() -> bool:
    """Test publishing to to_agent channel (simulating adapter -> orchestrator)."""
    from .core.bus import RedisBus, CHANNEL_TO_AGENT

    logger.info("Testing to_agent channel (adapter -> orchestrator)...")

    bus = RedisBus("redis://localhost:6379")
    try:
        await bus.connect()
    except ConnectionError:
        logger.error("❌ Cannot connect to Redis")
        return False

    received: list[str] = []
    event = asyncio.Event()

    async def handler(data: str) -> None:
        received.append(data)
        event.set()

    # Subscribe (simulating orchestrator)
    await bus.subscribe(CHANNEL_TO_AGENT, handler)
    await asyncio.sleep(0.3)

    # Publish test message (simulating adapter)
    test_msg = {
        "type": "idea_submit",
        "payload": {"content": "Test idea from integration test"},
        "source": "test",
        "user_id": "test_user",
        "timestamp": datetime.utcnow().isoformat(),
    }
    await bus.publish(CHANNEL_TO_AGENT, test_msg)

    # Wait for message
    try:
        await asyncio.wait_for(event.wait(), timeout=5.0)
    except asyncio.TimeoutError:
        logger.error("❌ Timeout waiting for to_agent message")
        await bus.disconnect()
        return False

    if received:
        data = json.loads(received[0])
        if data.get("type") == "idea_submit":
            logger.info("✅ to_agent channel test successful")
            await bus.disconnect()
            return True

    logger.error("❌ Message content mismatch")
    await bus.disconnect()
    return False


# ============================================================================
# Web API Tests
# ============================================================================

async def test_web_api_status(base_url: str = "http://localhost:8000") -> bool:
    """Test the web API status endpoint."""
    logger.info(f"Testing web API status at {base_url}/api/status...")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{base_url}/api/status", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                logger.info(f"  Status: {data.get('status')}")
                logger.info(f"  Mode: {data.get('mode')}")
                logger.info(f"  Redis: {data.get('redis_connected')}")
                logger.info("✅ Web API status endpoint working")
                return True
            else:
                logger.error(f"❌ Status endpoint returned {response.status_code}")
                return False
        except httpx.ConnectError:
            logger.error(f"❌ Cannot connect to web server at {base_url}")
            logger.error("Make sure the web adapter is running (ENV=web or ENV=both)")
            return False
        except Exception as e:
            logger.error(f"❌ Error testing status endpoint: {e}")
            return False


async def test_web_api_feed(base_url: str = "http://localhost:8000") -> bool:
    """Test the web API feed endpoint."""
    logger.info(f"Testing web API feed at {base_url}/api/feed...")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{base_url}/api/feed", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                logger.info(f"  Feed items: {data.get('count', 0)}")
                logger.info("✅ Web API feed endpoint working")
                return True
            else:
                logger.error(f"❌ Feed endpoint returned {response.status_code}")
                return False
        except httpx.ConnectError:
            logger.error(f"❌ Cannot connect to web server at {base_url}")
            return False
        except Exception as e:
            logger.error(f"❌ Error testing feed endpoint: {e}")
            return False


async def test_web_api_commands(base_url: str = "http://localhost:8000") -> bool:
    """Test the web API command endpoint."""
    logger.info(f"Testing web API commands at {base_url}/api/command...")

    async with httpx.AsyncClient() as client:
        try:
            # Test pause command
            response = await client.post(
                f"{base_url}/api/command",
                json={"command": "pause", "user_id": "test_user"},
                timeout=5.0,
            )
            if response.status_code != 200:
                logger.error(f"❌ Pause command failed: {response.status_code}")
                return False
            logger.info("  Pause command: OK")

            # Test go command
            response = await client.post(
                f"{base_url}/api/command",
                json={"command": "go", "user_id": "test_user"},
                timeout=5.0,
            )
            if response.status_code != 200:
                logger.error(f"❌ Go command failed: {response.status_code}")
                return False
            logger.info("  Go command: OK")

            # Test status command
            response = await client.post(
                f"{base_url}/api/command",
                json={"command": "status", "user_id": "test_user"},
                timeout=5.0,
            )
            if response.status_code != 200:
                logger.error(f"❌ Status command failed: {response.status_code}")
                return False
            logger.info("  Status command: OK")

            # Test idea command
            response = await client.post(
                f"{base_url}/api/command",
                json={
                    "command": "idea",
                    "args": {"content": "Test idea from integration test"},
                    "user_id": "test_user",
                },
                timeout=5.0,
            )
            if response.status_code != 200:
                logger.error(f"❌ Idea command failed: {response.status_code}")
                return False
            logger.info("  Idea command: OK")

            logger.info("✅ Web API command endpoint working")
            return True

        except httpx.ConnectError:
            logger.error(f"❌ Cannot connect to web server at {base_url}")
            return False
        except Exception as e:
            logger.error(f"❌ Error testing command endpoint: {e}")
            return False


async def test_websocket_connection(base_url: str = "http://localhost:8000") -> bool:
    """Test WebSocket connection to the web adapter."""
    import websockets.client as websockets_client

    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
    logger.info(f"Testing WebSocket connection at {ws_url}...")

    try:
        async with websockets_client.connect(ws_url) as ws:
            # Send ping
            await ws.send("ping")
            response = await asyncio.wait_for(ws.recv(), timeout=5.0)

            if response == "pong":
                logger.info("  Ping/pong: OK")
                logger.info("✅ WebSocket connection working")
                return True
            else:
                logger.error(f"❌ Unexpected response: {response}")
                return False

    except asyncio.TimeoutError:
        logger.error("❌ WebSocket timeout")
        return False
    except Exception as e:
        logger.error(f"❌ WebSocket connection failed: {e}")
        logger.error("Make sure the web adapter is running")
        return False


async def test_websocket_receives_redis(base_url: str = "http://localhost:8000") -> bool:
    """Test that WebSocket receives messages from Redis."""
    import websockets.client as websockets_client
    from .core.bus import RedisBus, CHANNEL_FROM_AGENT

    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
    logger.info("Testing WebSocket receives Redis messages...")

    # Connect to Redis
    bus = RedisBus("redis://localhost:6379")
    try:
        await bus.connect()
    except ConnectionError:
        logger.error("❌ Cannot connect to Redis")
        return False

    try:
        async with websockets_client.connect(ws_url) as ws:
            # Allow time for WebSocket to subscribe to Redis
            await asyncio.sleep(0.5)

            # Publish a test message to Redis
            test_msg = create_status_update("WebSocket integration test message")
            await bus.publish(CHANNEL_FROM_AGENT, test_msg)

            # Wait for message via WebSocket
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(response)

                if data.get("type") == "status_update":
                    logger.info("✅ WebSocket receives Redis messages correctly")
                    return True
                else:
                    logger.error(f"❌ Unexpected message type: {data.get('type')}")
                    return False

            except asyncio.TimeoutError:
                logger.error("❌ Timeout waiting for WebSocket message")
                return False

    except Exception as e:
        logger.error(f"❌ WebSocket test failed: {e}")
        return False
    finally:
        await bus.disconnect()


# ============================================================================
# Test Runners
# ============================================================================

async def run_redis_tests() -> tuple[int, int]:
    """Run all Redis-related tests.

    Returns:
        Tuple of (passed, failed) counts.
    """
    passed = 0
    failed = 0

    tests = [
        ("Redis Connection", test_redis_connection),
        ("Pub/Sub Roundtrip", test_pubsub_roundtrip),
        ("To-Agent Channel", test_to_agent_channel),
    ]

    for name, test_func in tests:
        logger.info(f"\n--- {name} ---")
        try:
            if await test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            logger.error(f"❌ Test crashed: {e}")
            failed += 1

    return passed, failed


async def run_web_tests(base_url: str = "http://localhost:8000") -> tuple[int, int]:
    """Run all web API tests.

    Args:
        base_url: Base URL of the web adapter.

    Returns:
        Tuple of (passed, failed) counts.
    """
    passed = 0
    failed = 0

    tests = [
        ("Web API Status", lambda: test_web_api_status(base_url)),
        ("Web API Feed", lambda: test_web_api_feed(base_url)),
        ("Web API Commands", lambda: test_web_api_commands(base_url)),
        ("WebSocket Connection", lambda: test_websocket_connection(base_url)),
        ("WebSocket Redis Integration", lambda: test_websocket_receives_redis(base_url)),
    ]

    for name, test_func in tests:
        logger.info(f"\n--- {name} ---")
        try:
            if await test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            logger.error(f"❌ Test crashed: {e}")
            failed += 1

    return passed, failed


async def run_all_tests(web_url: str | None = None) -> bool:
    """Run all integration tests.

    Args:
        web_url: URL of web adapter, or None to skip web tests.

    Returns:
        True if all tests passed.
    """
    logger.info("=" * 60)
    logger.info("FULLSEND INTEGRATION TESTS")
    logger.info("=" * 60)

    total_passed = 0
    total_failed = 0

    # Redis tests
    logger.info("\n[REDIS TESTS]")
    passed, failed = await run_redis_tests()
    total_passed += passed
    total_failed += failed

    # Web tests (if URL provided or testing locally)
    if web_url:
        logger.info("\n[WEB API TESTS]")
        passed, failed = await run_web_tests(web_url)
        total_passed += passed
        total_failed += failed
    else:
        logger.info("\n[WEB API TESTS - SKIPPED]")
        logger.info("Use --web-url http://localhost:8000 to run web tests")

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Passed: {total_passed}")
    logger.info(f"Failed: {total_failed}")

    if total_failed == 0:
        logger.info("\n✅ ALL TESTS PASSED")
        return True
    else:
        logger.error(f"\n❌ {total_failed} TEST(S) FAILED")
        return False


# ============================================================================
# Main Entry Point
# ============================================================================

def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Integration tests for Fullsend Discord Communication Service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run Redis tests only:
  python -m services.discord.test_integration

  # Run Redis + Web API tests:
  python -m services.discord.test_integration --web-url http://localhost:8000

  # Send mock agent messages (for manual testing):
  python -m services.discord.test_integration --send-mock
        """,
    )
    parser.add_argument(
        "--web-url",
        type=str,
        default=None,
        help="URL of the web adapter to test (e.g., http://localhost:8000)",
    )
    parser.add_argument(
        "--send-mock",
        action="store_true",
        help="Send mock agent messages to Redis (for manual Discord/Web testing)",
    )

    args = parser.parse_args()

    if args.send_mock:
        logger.info("Sending mock agent messages...")
        success = asyncio.run(send_mock_agent_messages())
        sys.exit(0 if success else 1)

    # Run integration tests
    success = asyncio.run(run_all_tests(args.web_url))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
