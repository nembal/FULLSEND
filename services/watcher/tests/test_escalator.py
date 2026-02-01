"""Unit tests for the escalator module."""

from datetime import datetime, timezone

import pytest

from services.watcher.classifier import Classification
from services.watcher.escalator import (
    EscalationContext,
    EscalationPayload,
    build_error_escalation,
    build_escalation,
)


class TestEscalationContext:
    """Tests for EscalationContext model."""

    def test_context_all_fields(self):
        """Test creating context with all fields."""
        context = EscalationContext(
            channel="gtm-ideas",
            user="jake",
            summary="User suggests scraping GitHub stargazers",
        )

        assert context.channel == "gtm-ideas"
        assert context.user == "jake"
        assert context.summary == "User suggests scraping GitHub stargazers"


class TestEscalationPayload:
    """Tests for EscalationPayload model."""

    def test_payload_defaults(self):
        """Test that type and source have correct defaults."""
        payload = EscalationPayload(
            priority="high",
            reason="Test reason",
            original_message={"content": "test"},
            context=EscalationContext(
                channel="test-channel",
                user="test-user",
                summary="Test summary",
            ),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        assert payload.type == "escalation"
        assert payload.source == "watcher"

    def test_payload_serialization(self):
        """Test that payload can be serialized to JSON."""
        payload = EscalationPayload(
            priority="high",
            reason="New GTM idea",
            original_message={"content": "What about LinkedIn scraping?"},
            context=EscalationContext(
                channel="ideas",
                user="founder",
                summary="LinkedIn scraping suggestion",
            ),
            timestamp="2024-01-15T10:30:00+00:00",
        )

        json_str = payload.model_dump_json()
        assert '"type":"escalation"' in json_str.replace(" ", "")
        assert '"source":"watcher"' in json_str.replace(" ", "")
        assert '"priority":"high"' in json_str.replace(" ", "")


class TestBuildEscalation:
    """Tests for build_escalation function."""

    def test_builds_correct_payload_shape(self):
        """Test that build_escalation returns correct payload shape."""
        msg = {
            "content": "What about scraping GitHub stargazers?",
            "username": "jake",
            "channel_name": "gtm-ideas",
            "channel_id": "123",
            "message_id": "456",
        }
        classification = Classification(
            action="escalate",
            reason="New GTM idea from user",
            priority="high",
        )

        result = build_escalation(msg, classification)

        assert result.type == "escalation"
        assert result.source == "watcher"
        assert result.priority == "high"
        assert result.reason == "New GTM idea from user"
        assert result.original_message == msg
        assert result.context.channel == "gtm-ideas"
        assert result.context.user == "jake"
        assert result.context.summary == "New GTM idea from user"
        assert result.timestamp is not None

    def test_handles_missing_fields_with_defaults(self):
        """Test that missing message fields get 'unknown' defaults."""
        msg = {"content": "Hello"}
        classification = Classification(
            action="escalate",
            reason="Test reason",
            priority="medium",
        )

        result = build_escalation(msg, classification)

        assert result.context.channel == "unknown"
        assert result.context.user == "unknown"

    def test_custom_summary_overrides_reason(self):
        """Test that custom summary parameter is used when provided."""
        msg = {
            "content": "Help!",
            "username": "user",
            "channel_name": "support",
        }
        classification = Classification(
            action="escalate",
            reason="Urgent keyword detected",
            priority="urgent",
        )

        result = build_escalation(msg, classification, summary="Custom: User needs help")

        assert result.context.summary == "Custom: User needs help"
        assert result.reason == "Urgent keyword detected"  # Reason unchanged

    def test_includes_timestamp(self):
        """Test that escalation includes ISO8601 timestamp."""
        msg = {"content": "test", "username": "user", "channel_name": "test"}
        classification = Classification(
            action="escalate",
            reason="Test",
            priority="low",
        )

        result = build_escalation(msg, classification)

        # Verify timestamp is ISO format
        assert "T" in result.timestamp
        assert "+" in result.timestamp or "Z" in result.timestamp

    def test_preserves_all_priorities(self):
        """Test all priority levels are preserved correctly."""
        msg = {"content": "test", "username": "user", "channel_name": "test"}

        for priority in ["low", "medium", "high", "urgent"]:
            classification = Classification(
                action="escalate",
                reason="Test",
                priority=priority,  # type: ignore
            )
            result = build_escalation(msg, classification)
            assert result.priority == priority


class TestBuildErrorEscalation:
    """Tests for build_error_escalation function."""

    def test_builds_error_payload(self):
        """Test building escalation for error conditions."""
        msg = {
            "content": "What's the status?",
            "username": "user",
            "channel_name": "general",
        }
        error = ValueError("API rate limit exceeded")

        result = build_error_escalation(msg, error, error_type="classification_failed")

        assert result.type == "escalation"
        assert result.source == "watcher"
        assert result.priority == "medium"  # Errors get medium priority
        assert "classification_failed" in result.reason
        assert "API rate limit exceeded" in result.reason
        assert "classification_failed" in result.context.summary

    def test_error_payload_preserves_original_message(self):
        """Test that original message is preserved in error escalation."""
        msg = {
            "content": "Help",
            "username": "jake",
            "channel_name": "support",
            "message_id": "789",
        }
        error = Exception("Connection timeout")

        result = build_error_escalation(msg, error)

        assert result.original_message == msg
        assert result.context.user == "jake"
        assert result.context.channel == "support"

    def test_default_error_type(self):
        """Test default error_type is used when not specified."""
        msg = {"content": "test", "username": "user", "channel_name": "test"}
        error = Exception("Generic error")

        result = build_error_escalation(msg, error)

        assert "classification_error" in result.reason

    def test_error_escalation_summary(self):
        """Test error escalation context summary format."""
        msg = {"content": "test", "username": "user", "channel_name": "test"}
        error = Exception("Test error")

        result = build_error_escalation(
            msg,
            error,
            error_type="response_generation_failed_after_3_attempts",
        )

        assert "response_generation_failed_after_3_attempts" in result.context.summary
        assert "escalating for human review" in result.context.summary


class TestPublishEscalation:
    """Tests for publish_escalation function."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        from unittest.mock import AsyncMock

        redis_client = AsyncMock()
        return redis_client

    @pytest.mark.asyncio
    async def test_publishes_to_correct_channel(self, mock_redis):
        """Test that escalation is published to specified channel."""
        from services.watcher.escalator import publish_escalation

        payload = EscalationPayload(
            priority="high",
            reason="Test",
            original_message={"content": "test"},
            context=EscalationContext(
                channel="test",
                user="user",
                summary="Test",
            ),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        await publish_escalation(payload, mock_redis, "fullsend:to_orchestrator")

        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        assert call_args[0][0] == "fullsend:to_orchestrator"

    @pytest.mark.asyncio
    async def test_publishes_json_payload(self, mock_redis):
        """Test that payload is serialized as JSON."""
        from services.watcher.escalator import publish_escalation
        import json

        payload = EscalationPayload(
            priority="high",
            reason="Test reason",
            original_message={"content": "test"},
            context=EscalationContext(
                channel="test",
                user="user",
                summary="Test",
            ),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        await publish_escalation(payload, mock_redis, "channel")

        call_args = mock_redis.publish.call_args
        published_json = call_args[0][1]

        # Verify it's valid JSON
        parsed = json.loads(published_json)
        assert parsed["type"] == "escalation"
        assert parsed["priority"] == "high"
        assert parsed["reason"] == "Test reason"
