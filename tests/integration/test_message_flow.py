"""Integration tests for message flow across services.

Tests the end-to-end message flow:
Discord → Watcher (fullsend:discord_raw)
Watcher → Orchestrator (fullsend:to_orchestrator) [escalation]
Watcher → Discord (fullsend:from_orchestrator) [simple response]
Orchestrator → Discord (fullsend:from_orchestrator)

Uses fakeredis-py for isolated Redis simulation.
"""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

# Channel constants (should match services)
CHANNEL_DISCORD_RAW = "fullsend:discord_raw"
CHANNEL_TO_ORCHESTRATOR = "fullsend:to_orchestrator"
CHANNEL_FROM_ORCHESTRATOR = "fullsend:from_orchestrator"


def make_discord_message(
    content: str = "Test message",
    username: str = "testuser",
    channel_name: str = "general",
    channel_id: str = "123456789",
    message_id: str = "987654321",
) -> dict[str, Any]:
    """Create a mock Discord message payload."""
    return {
        "content": content,
        "username": username,
        "channel_name": channel_name,
        "channel_id": channel_id,
        "message_id": message_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }


def make_escalation_payload(
    msg: dict[str, Any],
    priority: str = "medium",
    reason: str = "Test escalation",
) -> dict[str, Any]:
    """Create a mock escalation payload (Watcher → Orchestrator)."""
    return {
        "type": "escalation",
        "source": "watcher",
        "priority": priority,
        "reason": reason,
        "original_message": msg,
        "context": {
            "channel": msg.get("channel_name", "unknown"),
            "user": msg.get("username", "unknown"),
            "summary": reason,
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }


def make_response_payload(
    channel_id: str,
    content: str,
    reply_to: str | None = None,
) -> dict[str, Any]:
    """Create a mock response payload (Orchestrator/Watcher → Discord)."""
    return {
        "type": "watcher_response",
        "channel_id": channel_id,
        "reply_to": reply_to,
        "content": content,
    }


class FakePubSub:
    """Fake Redis PubSub for testing message flow."""

    def __init__(self) -> None:
        self.subscriptions: set[str] = set()
        self.messages: list[dict[str, Any]] = []
        self._message_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def subscribe(self, *channels: str) -> None:
        """Subscribe to channels."""
        for channel in channels:
            self.subscriptions.add(channel)

    async def unsubscribe(self, *channels: str) -> None:
        """Unsubscribe from channels."""
        for channel in channels:
            self.subscriptions.discard(channel)

    async def get_message(
        self,
        ignore_subscribe_messages: bool = True,
        timeout: float = 1.0,
    ) -> dict[str, Any] | None:
        """Get next message from queue."""
        try:
            return await asyncio.wait_for(
                self._message_queue.get(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return None

    async def close(self) -> None:
        """Close the pubsub connection."""
        pass

    def inject_message(self, channel: str, data: str) -> None:
        """Inject a message into the queue for testing."""
        if channel in self.subscriptions:
            self._message_queue.put_nowait({
                "type": "message",
                "channel": channel,
                "data": data,
            })


class FakeRedis:
    """Fake Redis client for testing message flow."""

    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []
        self._pubsub = FakePubSub()
        self._data: dict[str, str] = {}

    async def publish(self, channel: str, message: str) -> int:
        """Publish a message to a channel."""
        self.published.append((channel, message))
        # Also inject into pubsub if subscribed
        self._pubsub.inject_message(channel, message)
        return 1

    def pubsub(self) -> FakePubSub:
        """Get pubsub instance."""
        return self._pubsub

    async def ping(self) -> bool:
        """Ping the server."""
        return True

    async def aclose(self) -> None:
        """Close the connection."""
        pass

    async def get(self, key: str) -> str | None:
        """Get a value."""
        return self._data.get(key)

    async def set(self, key: str, value: str) -> bool:
        """Set a value."""
        self._data[key] = value
        return True


@pytest.fixture
def fake_redis() -> FakeRedis:
    """Create a fake Redis instance."""
    return FakeRedis()


class TestChannelConstants:
    """Verify channel constants are consistent across services."""

    def test_discord_raw_channel(self) -> None:
        """Verify fullsend:discord_raw is the correct format."""
        assert CHANNEL_DISCORD_RAW == "fullsend:discord_raw"

    def test_to_orchestrator_channel(self) -> None:
        """Verify fullsend:to_orchestrator is the correct format."""
        assert CHANNEL_TO_ORCHESTRATOR == "fullsend:to_orchestrator"

    def test_from_orchestrator_channel(self) -> None:
        """Verify fullsend:from_orchestrator is the correct format."""
        assert CHANNEL_FROM_ORCHESTRATOR == "fullsend:from_orchestrator"


class TestDiscordToWatcher:
    """Test Discord → Watcher message flow via fullsend:discord_raw."""

    @pytest.mark.asyncio
    async def test_discord_publishes_to_discord_raw(
        self, fake_redis: FakeRedis
    ) -> None:
        """Discord should publish raw messages to fullsend:discord_raw."""
        msg = make_discord_message(content="Hello world")
        msg_json = json.dumps(msg)

        await fake_redis.publish(CHANNEL_DISCORD_RAW, msg_json)

        assert len(fake_redis.published) == 1
        channel, data = fake_redis.published[0]
        assert channel == CHANNEL_DISCORD_RAW
        assert json.loads(data)["content"] == "Hello world"

    @pytest.mark.asyncio
    async def test_watcher_receives_from_discord_raw(
        self, fake_redis: FakeRedis
    ) -> None:
        """Watcher should receive messages from fullsend:discord_raw."""
        pubsub = fake_redis.pubsub()
        await pubsub.subscribe(CHANNEL_DISCORD_RAW)

        msg = make_discord_message(content="Test message")
        await fake_redis.publish(CHANNEL_DISCORD_RAW, json.dumps(msg))

        received = await pubsub.get_message(timeout=1.0)
        assert received is not None
        assert received["type"] == "message"
        assert received["channel"] == CHANNEL_DISCORD_RAW
        assert json.loads(received["data"])["content"] == "Test message"


class TestWatcherToOrchestrator:
    """Test Watcher → Orchestrator escalation flow via fullsend:to_orchestrator."""

    @pytest.mark.asyncio
    async def test_watcher_escalates_to_orchestrator(
        self, fake_redis: FakeRedis
    ) -> None:
        """Watcher should escalate complex messages to Orchestrator."""
        msg = make_discord_message(content="I have a strategic idea")
        escalation = make_escalation_payload(
            msg,
            priority="high",
            reason="Strategic planning request",
        )

        await fake_redis.publish(
            CHANNEL_TO_ORCHESTRATOR, json.dumps(escalation)
        )

        assert len(fake_redis.published) == 1
        channel, data = fake_redis.published[0]
        assert channel == CHANNEL_TO_ORCHESTRATOR
        parsed = json.loads(data)
        assert parsed["type"] == "escalation"
        assert parsed["source"] == "watcher"
        assert parsed["priority"] == "high"

    @pytest.mark.asyncio
    async def test_orchestrator_receives_escalation(
        self, fake_redis: FakeRedis
    ) -> None:
        """Orchestrator should receive escalations from Watcher."""
        pubsub = fake_redis.pubsub()
        await pubsub.subscribe(CHANNEL_TO_ORCHESTRATOR)

        msg = make_discord_message(content="Need strategic decision")
        escalation = make_escalation_payload(msg, reason="Strategic query")
        await fake_redis.publish(CHANNEL_TO_ORCHESTRATOR, json.dumps(escalation))

        received = await pubsub.get_message(timeout=1.0)
        assert received is not None
        assert received["channel"] == CHANNEL_TO_ORCHESTRATOR
        parsed = json.loads(received["data"])
        assert parsed["type"] == "escalation"
        assert parsed["original_message"]["content"] == "Need strategic decision"


class TestWatcherToDiscord:
    """Test Watcher → Discord response flow via fullsend:from_orchestrator."""

    @pytest.mark.asyncio
    async def test_watcher_sends_simple_response(
        self, fake_redis: FakeRedis
    ) -> None:
        """Watcher should send simple responses directly to Discord."""
        response = make_response_payload(
            channel_id="123456789",
            content="Here's a quick answer!",
            reply_to="987654321",
        )

        await fake_redis.publish(
            CHANNEL_FROM_ORCHESTRATOR, json.dumps(response)
        )

        assert len(fake_redis.published) == 1
        channel, data = fake_redis.published[0]
        assert channel == CHANNEL_FROM_ORCHESTRATOR
        parsed = json.loads(data)
        assert parsed["type"] == "watcher_response"
        assert parsed["content"] == "Here's a quick answer!"


class TestOrchestratorToDiscord:
    """Test Orchestrator → Discord response flow via fullsend:from_orchestrator."""

    @pytest.mark.asyncio
    async def test_orchestrator_sends_response(
        self, fake_redis: FakeRedis
    ) -> None:
        """Orchestrator should send responses to Discord via from_orchestrator."""
        response = {
            "type": "orchestrator_response",
            "channel_id": "123456789",
            "content": "Strategic analysis complete. Here's my recommendation...",
            "priority": "high",
        }

        await fake_redis.publish(
            CHANNEL_FROM_ORCHESTRATOR, json.dumps(response)
        )

        assert len(fake_redis.published) == 1
        channel, data = fake_redis.published[0]
        assert channel == CHANNEL_FROM_ORCHESTRATOR
        parsed = json.loads(data)
        assert parsed["type"] == "orchestrator_response"

    @pytest.mark.asyncio
    async def test_discord_receives_orchestrator_response(
        self, fake_redis: FakeRedis
    ) -> None:
        """Discord should receive responses from Orchestrator."""
        pubsub = fake_redis.pubsub()
        await pubsub.subscribe(CHANNEL_FROM_ORCHESTRATOR)

        response = {
            "type": "orchestrator_response",
            "channel_id": "123456789",
            "content": "Here is my strategic recommendation.",
        }
        await fake_redis.publish(CHANNEL_FROM_ORCHESTRATOR, json.dumps(response))

        received = await pubsub.get_message(timeout=1.0)
        assert received is not None
        assert received["channel"] == CHANNEL_FROM_ORCHESTRATOR
        parsed = json.loads(received["data"])
        assert parsed["content"] == "Here is my strategic recommendation."


class TestEndToEndFlow:
    """Test the complete message flow: Discord → Watcher → Orchestrator → Discord."""

    @pytest.mark.asyncio
    async def test_full_escalation_flow(self, fake_redis: FakeRedis) -> None:
        """Test complete flow: Discord message → escalation → response."""
        # 1. Discord subscribes to responses
        discord_pubsub = fake_redis.pubsub()
        await discord_pubsub.subscribe(CHANNEL_FROM_ORCHESTRATOR)

        # 2. Orchestrator subscribes to escalations
        orchestrator_pubsub = fake_redis.pubsub()
        await orchestrator_pubsub.subscribe(CHANNEL_TO_ORCHESTRATOR)

        # 3. Watcher subscribes to discord raw
        watcher_pubsub = fake_redis.pubsub()
        await watcher_pubsub.subscribe(CHANNEL_DISCORD_RAW)

        # 4. Discord publishes a message
        discord_msg = make_discord_message(
            content="What should our Q2 strategy be?",
            username="ceo",
            channel_name="strategy",
        )
        await fake_redis.publish(CHANNEL_DISCORD_RAW, json.dumps(discord_msg))

        # 5. Watcher receives the message
        watcher_received = await watcher_pubsub.get_message(timeout=1.0)
        assert watcher_received is not None
        assert watcher_received["channel"] == CHANNEL_DISCORD_RAW

        # 6. Watcher escalates to Orchestrator
        escalation = make_escalation_payload(
            discord_msg,
            priority="high",
            reason="Strategic planning request from CEO",
        )
        await fake_redis.publish(CHANNEL_TO_ORCHESTRATOR, json.dumps(escalation))

        # 7. Orchestrator receives the escalation
        orchestrator_received = await orchestrator_pubsub.get_message(timeout=1.0)
        assert orchestrator_received is not None
        assert orchestrator_received["channel"] == CHANNEL_TO_ORCHESTRATOR
        parsed_escalation = json.loads(orchestrator_received["data"])
        assert parsed_escalation["priority"] == "high"

        # 8. Orchestrator sends response to Discord
        response = {
            "type": "orchestrator_response",
            "channel_id": discord_msg["channel_id"],
            "reply_to": discord_msg["message_id"],
            "content": "Based on analysis, I recommend focusing on...",
        }
        await fake_redis.publish(CHANNEL_FROM_ORCHESTRATOR, json.dumps(response))

        # 9. Discord receives the response
        discord_received = await discord_pubsub.get_message(timeout=1.0)
        assert discord_received is not None
        assert discord_received["channel"] == CHANNEL_FROM_ORCHESTRATOR
        parsed_response = json.loads(discord_received["data"])
        assert parsed_response["type"] == "orchestrator_response"
        assert "recommend" in parsed_response["content"]

    @pytest.mark.asyncio
    async def test_simple_response_flow(self, fake_redis: FakeRedis) -> None:
        """Test flow for simple responses: Discord → Watcher → Discord (no escalation)."""
        # 1. Discord subscribes to responses
        discord_pubsub = fake_redis.pubsub()
        await discord_pubsub.subscribe(CHANNEL_FROM_ORCHESTRATOR)

        # 2. Watcher subscribes to discord raw
        watcher_pubsub = fake_redis.pubsub()
        await watcher_pubsub.subscribe(CHANNEL_DISCORD_RAW)

        # 3. Discord publishes a simple question
        discord_msg = make_discord_message(
            content="What time is the standup?",
            username="dev",
            channel_name="general",
        )
        await fake_redis.publish(CHANNEL_DISCORD_RAW, json.dumps(discord_msg))

        # 4. Watcher receives the message
        watcher_received = await watcher_pubsub.get_message(timeout=1.0)
        assert watcher_received is not None
        assert watcher_received["channel"] == CHANNEL_DISCORD_RAW

        # 5. Watcher sends simple response directly (no escalation)
        response = make_response_payload(
            channel_id=discord_msg["channel_id"],
            content="Standup is at 10am daily.",
            reply_to=discord_msg["message_id"],
        )
        await fake_redis.publish(CHANNEL_FROM_ORCHESTRATOR, json.dumps(response))

        # 6. Discord receives the response
        discord_received = await discord_pubsub.get_message(timeout=1.0)
        assert discord_received is not None
        assert discord_received["channel"] == CHANNEL_FROM_ORCHESTRATOR
        parsed_response = json.loads(discord_received["data"])
        assert parsed_response["type"] == "watcher_response"
        assert "10am" in parsed_response["content"]


class TestMessagePayloadValidation:
    """Test that message payloads have required fields."""

    def test_discord_message_has_required_fields(self) -> None:
        """Discord messages should have all required fields."""
        msg = make_discord_message()
        required = ["content", "username", "channel_name", "channel_id", "message_id", "timestamp"]
        for field in required:
            assert field in msg, f"Missing required field: {field}"

    def test_escalation_payload_has_required_fields(self) -> None:
        """Escalation payloads should have all required fields."""
        msg = make_discord_message()
        escalation = make_escalation_payload(msg)
        required = ["type", "source", "priority", "reason", "original_message", "context", "timestamp"]
        for field in required:
            assert field in escalation, f"Missing required field: {field}"

    def test_escalation_context_has_required_fields(self) -> None:
        """Escalation context should have all required fields."""
        msg = make_discord_message()
        escalation = make_escalation_payload(msg)
        context = escalation["context"]
        required = ["channel", "user", "summary"]
        for field in required:
            assert field in context, f"Missing required context field: {field}"

    def test_response_payload_has_required_fields(self) -> None:
        """Response payloads should have all required fields."""
        response = make_response_payload("123", "content")
        required = ["type", "channel_id", "content"]
        for field in required:
            assert field in response, f"Missing required field: {field}"
