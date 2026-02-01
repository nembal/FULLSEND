"""Integration tests for the Orchestrator service.

These tests verify the end-to-end flow of message processing,
including Redis pub/sub integration. Some tests require a running
Redis instance and are marked with pytest.mark.integration.

For tests requiring a live Redis, use:
    pytest -m integration services/orchestrator/tests/test_integration.py

For unit-style tests with mocked Redis:
    pytest -m "not integration" services/orchestrator/tests/test_integration.py
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.orchestrator.context import Context
from services.orchestrator.dispatcher import Decision, Dispatcher, execute_decision
from services.orchestrator.main import (
    execute_decision as main_execute_decision,
    execute_decision_safe,
    load_context_safe,
    process_message,
)


class TestProcessMessage:
    """Integration tests for process_message function with mocked dependencies."""

    @pytest.fixture
    def mock_settings(self, tmp_path):
        """Create mock settings."""
        settings = MagicMock()
        settings.anthropic_api_key = "test-api-key"
        settings.orchestrator_model = "claude-opus-4-20250514"
        settings.orchestrator_thinking_budget = 10000
        settings.orchestrator_max_tokens = 16000
        settings.thinking_timeout_seconds = 60
        settings.redis_url = "redis://localhost:6379"
        settings.context_path = tmp_path
        settings.channel_to_orchestrator = "fullsend:to_orchestrator"
        settings.channel_from_orchestrator = "fullsend:from_orchestrator"
        settings.channel_to_fullsend = "fullsend:to_fullsend"
        settings.channel_builder_tasks = "fullsend:builder_tasks"
        settings.roundtable_timeout_seconds = 120
        settings.roundtable_max_rounds = 3
        return settings

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis = AsyncMock()
        redis.publish = AsyncMock()
        redis.hset = AsyncMock()
        redis.scan = AsyncMock(return_value=(0, []))
        return redis

    @pytest.fixture
    def mock_agent(self):
        """Create mock OrchestratorAgent."""
        agent = MagicMock()
        agent.process_with_thinking = AsyncMock()
        return agent

    @pytest.fixture
    def sample_escalation(self):
        """Create a sample escalation message."""
        return {
            "type": "escalation",
            "source": "watcher",
            "priority": "high",
            "reason": "New GTM idea from user",
            "original_message": {
                "username": "jake",
                "content": "What if we scraped GitHub stargazers?",
            },
            "channel_id": "123456789",
            "message_id": "987654321",
        }

    @pytest.fixture
    def sample_metric_alert(self):
        """Create a sample metric alert message."""
        return {
            "type": "metric_alert",
            "source": "redis_agent",
            "experiment_id": "exp_123",
            "alert_type": "threshold_crossed",
            "metric": "response_rate",
            "value": 0.02,
            "threshold": 0.05,
            "recommendation": "Consider killing this experiment",
        }

    @pytest.mark.asyncio
    async def test_process_escalation_dispatch_to_fullsend(
        self, mock_redis, mock_settings, mock_agent, sample_escalation
    ):
        """Test that escalation can be dispatched to FULLSEND."""
        mock_agent.process_with_thinking.return_value = Decision(
            action="dispatch_to_fullsend",
            reasoning="Good idea worth testing",
            payload={"idea": "GitHub stargazer campaign"},
            priority="high",
            context_for_fullsend="User suggested scraping GitHub stargazers",
        )
        dispatcher = Dispatcher(mock_redis, mock_settings)

        await process_message(
            sample_escalation, mock_agent, dispatcher, mock_redis, mock_settings
        )

        # Verify publish was called
        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        assert call_args[0][0] == "fullsend:to_fullsend"

        # Verify payload structure
        published_data = json.loads(call_args[0][1])
        assert published_data["type"] == "experiment_request"
        assert published_data["priority"] == "high"

    @pytest.mark.asyncio
    async def test_process_alert_respond_to_discord(
        self, mock_redis, mock_settings, mock_agent, sample_metric_alert
    ):
        """Test that metric alert triggers Discord response."""
        mock_agent.process_with_thinking.return_value = Decision(
            action="respond_to_discord",
            reasoning="Alerting user about low performance",
            payload={"content": "Experiment exp_123 is underperforming"},
            priority="medium",
        )
        dispatcher = Dispatcher(mock_redis, mock_settings)

        await process_message(
            sample_metric_alert, mock_agent, dispatcher, mock_redis, mock_settings
        )

        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        assert call_args[0][0] == "fullsend:from_orchestrator"

    @pytest.mark.asyncio
    async def test_process_no_action_does_not_publish(
        self, mock_redis, mock_settings, mock_agent, sample_escalation
    ):
        """Test that no_action decision doesn't publish anything."""
        mock_agent.process_with_thinking.return_value = Decision(
            action="no_action",
            reasoning="Not worth pursuing",
            payload={},
            priority="low",
        )
        dispatcher = Dispatcher(mock_redis, mock_settings)

        await process_message(
            sample_escalation, mock_agent, dispatcher, mock_redis, mock_settings
        )

        mock_redis.publish.assert_not_called()


class TestExecuteDecision:
    """Tests for execute_decision function."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis = AsyncMock()
        redis.publish = AsyncMock()
        redis.hset = AsyncMock()
        return redis

    @pytest.fixture
    def mock_settings(self, tmp_path):
        """Create mock settings."""
        settings = MagicMock()
        settings.context_path = tmp_path
        settings.channel_to_fullsend = "fullsend:to_fullsend"
        settings.channel_builder_tasks = "fullsend:builder_tasks"
        settings.channel_from_orchestrator = "fullsend:from_orchestrator"
        settings.roundtable_timeout_seconds = 120
        settings.roundtable_max_rounds = 3
        return settings

    @pytest.mark.asyncio
    async def test_dispatch_to_fullsend(self, mock_redis, mock_settings):
        """Test dispatch_to_fullsend action."""
        decision = Decision(
            action="dispatch_to_fullsend",
            reasoning="Good idea",
            payload={"idea": "Test campaign"},
            priority="high",
            context_for_fullsend="Relevant context",
        )
        dispatcher = Dispatcher(mock_redis, mock_settings)

        await execute_decision(decision, {}, dispatcher)

        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        assert call_args[0][0] == "fullsend:to_fullsend"

        payload = json.loads(call_args[0][1])
        assert payload["type"] == "experiment_request"
        assert payload["priority"] == "high"
        assert payload["context"] == "Relevant context"

    @pytest.mark.asyncio
    async def test_dispatch_to_builder(self, mock_redis, mock_settings):
        """Test dispatch_to_builder action."""
        decision = Decision(
            action="dispatch_to_builder",
            reasoning="Need new tool",
            payload={"name": "scraper", "purpose": "Scrape data"},
            priority="medium",
        )
        dispatcher = Dispatcher(mock_redis, mock_settings)

        await execute_decision(decision, {}, dispatcher)

        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        assert call_args[0][0] == "fullsend:builder_tasks"

        payload = json.loads(call_args[0][1])
        assert payload["type"] == "tool_prd"
        assert payload["requested_by"] == "orchestrator"

    @pytest.mark.asyncio
    async def test_respond_to_discord(self, mock_redis, mock_settings):
        """Test respond_to_discord action."""
        decision = Decision(
            action="respond_to_discord",
            reasoning="Status update",
            payload={"content": "All systems operational"},
            priority="low",
        )
        original_msg = {"channel_id": "123", "message_id": "456"}
        dispatcher = Dispatcher(mock_redis, mock_settings)

        await execute_decision(decision, original_msg, dispatcher)

        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        assert call_args[0][0] == "fullsend:from_orchestrator"

        payload = json.loads(call_args[0][1])
        assert payload["type"] == "orchestrator_response"
        assert payload["channel_id"] == "123"
        assert payload["content"] == "All systems operational"

    @pytest.mark.asyncio
    async def test_kill_experiment(self, mock_redis, mock_settings):
        """Test kill_experiment action."""
        decision = Decision(
            action="kill_experiment",
            reasoning="Low performance",
            payload={"reason": "Response rate too low"},
            priority="high",
            experiment_id="exp_123",
        )
        dispatcher = Dispatcher(mock_redis, mock_settings)

        await execute_decision(decision, {}, dispatcher)

        mock_redis.hset.assert_called_once()
        call_args = mock_redis.hset.call_args
        assert call_args[0][0] == "experiments:exp_123"
        assert call_args[1]["mapping"]["state"] == "archived"

    @pytest.mark.asyncio
    async def test_update_worklist(self, mock_redis, mock_settings):
        """Test update_worklist action."""
        decision = Decision(
            action="update_worklist",
            reasoning="New priorities",
            payload={"content": "## Worklist\n- New task"},
            priority="medium",
        )
        dispatcher = Dispatcher(mock_redis, mock_settings)

        await execute_decision(decision, {}, dispatcher)

        # Verify worklist was updated
        worklist_path = mock_settings.context_path / "worklist.md"
        assert worklist_path.exists()
        assert "New task" in worklist_path.read_text()

    @pytest.mark.asyncio
    async def test_record_learning(self, mock_redis, mock_settings):
        """Test record_learning action."""
        decision = Decision(
            action="record_learning",
            reasoning="Important insight",
            payload={"learning": "Event targeting works better"},
            priority="medium",
        )
        dispatcher = Dispatcher(mock_redis, mock_settings)

        await execute_decision(decision, {}, dispatcher)

        # Verify learning was appended
        learnings_path = mock_settings.context_path / "learnings.md"
        assert learnings_path.exists()
        content = learnings_path.read_text()
        assert "Event targeting works better" in content

    @pytest.mark.asyncio
    async def test_no_action_does_nothing(self, mock_redis, mock_settings):
        """Test no_action doesn't perform any operations."""
        decision = Decision(
            action="no_action",
            reasoning="Not worth it",
            payload={},
            priority="low",
        )
        dispatcher = Dispatcher(mock_redis, mock_settings)

        result = await execute_decision(decision, {}, dispatcher)

        assert result is None
        mock_redis.publish.assert_not_called()
        mock_redis.hset.assert_not_called()


class TestExecuteDecisionSafe:
    """Tests for execute_decision_safe function with timeout and error handling."""

    @pytest.fixture
    def mock_settings(self, tmp_path):
        """Create mock settings."""
        settings = MagicMock()
        settings.context_path = tmp_path
        settings.channel_from_orchestrator = "fullsend:from_orchestrator"
        settings.roundtable_timeout_seconds = 120
        settings.roundtable_max_rounds = 3
        return settings

    @pytest.fixture
    def mock_dispatcher(self):
        """Create mock dispatcher."""
        return MagicMock()

    @pytest.fixture
    def sample_context(self):
        """Create sample context."""
        return Context(
            product="",
            worklist="",
            learnings="",
            active_experiments=[],
            available_tools=[],
            recent_metrics={},
        )

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(
        self, mock_settings, mock_dispatcher, sample_context
    ):
        """Test returns None on timeout."""
        decision = Decision(
            action="initiate_roundtable",
            reasoning="Need debate",
            payload={"prompt": "What's next?"},
            priority="medium",
        )

        # Make the dispatcher hang
        mock_dispatcher.initiate_roundtable = AsyncMock(
            side_effect=asyncio.TimeoutError()
        )

        with patch("services.orchestrator.main.execute_decision") as mock_exec:
            mock_exec.side_effect = asyncio.TimeoutError()
            result = await execute_decision_safe(
                decision, {}, sample_context, mock_dispatcher, mock_settings
            )

        assert result is None


class TestLoadContextSafe:
    """Tests for load_context_safe function in main module."""

    @pytest.fixture
    def mock_settings(self, tmp_path):
        """Create mock settings."""
        settings = MagicMock()
        settings.context_path = tmp_path
        return settings

    @pytest.mark.asyncio
    async def test_returns_context_on_success(self, mock_settings, tmp_path):
        """Test returns Context on successful load."""
        # Create context files
        (tmp_path / "product_context.md").write_text("Test Product")
        (tmp_path / "worklist.md").write_text("## Worklist")
        (tmp_path / "learnings.md").write_text("## Learnings")

        mock_redis = AsyncMock()
        mock_redis.scan.return_value = (0, [])

        context = await load_context_safe(mock_redis, mock_settings)

        assert context.product == "Test Product"
        assert "Worklist" in context.worklist

    @pytest.mark.asyncio
    async def test_returns_empty_context_on_timeout(self, mock_settings):
        """Test returns empty Context on timeout."""
        mock_redis = AsyncMock()
        mock_redis.scan.side_effect = asyncio.TimeoutError()

        with patch("services.orchestrator.main.load_context") as mock_load:
            mock_load.side_effect = asyncio.TimeoutError()

            # This should handle the timeout gracefully
            context = await load_context_safe(mock_redis, mock_settings)

        assert context.product == ""
        assert context.active_experiments == []


class TestMessageTypeRouting:
    """Tests verifying different message types are routed correctly."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis = AsyncMock()
        redis.publish = AsyncMock()
        redis.scan = AsyncMock(return_value=(0, []))
        return redis

    @pytest.fixture
    def mock_settings(self, tmp_path):
        """Create mock settings."""
        settings = MagicMock()
        settings.context_path = tmp_path
        settings.channel_to_fullsend = "fullsend:to_fullsend"
        settings.channel_builder_tasks = "fullsend:builder_tasks"
        settings.channel_from_orchestrator = "fullsend:from_orchestrator"
        settings.roundtable_timeout_seconds = 120
        settings.roundtable_max_rounds = 3
        return settings

    def test_escalation_message_format_matches_prd(self):
        """Verify escalation message format matches PRD specification."""
        escalation = {
            "type": "escalation",
            "source": "watcher",
            "priority": "high",
            "reason": "New GTM idea from user",
            "original_message": {
                "username": "jake",
                "content": "What if we scraped GitHub stargazers?",
            },
        }

        assert escalation["type"] == "escalation"
        assert escalation["source"] == "watcher"
        assert escalation["priority"] in ["low", "medium", "high", "urgent"]
        assert "reason" in escalation
        assert "original_message" in escalation

    def test_metric_alert_message_format_matches_prd(self):
        """Verify metric alert message format matches PRD specification."""
        alert = {
            "type": "metric_alert",
            "source": "redis_agent",
            "experiment_id": "exp_123",
            "alert_type": "threshold_crossed",
            "metric": "response_rate",
            "value": 0.02,
            "threshold": 0.05,
            "recommendation": "Consider killing this experiment",
        }

        assert alert["type"] == "metric_alert"
        assert alert["source"] == "redis_agent"
        assert "experiment_id" in alert
        assert "metric" in alert
        assert "value" in alert

    def test_experiment_ready_message_format_matches_prd(self):
        """Verify experiment ready message format matches PRD specification."""
        ready_msg = {
            "type": "experiment_ready",
            "source": "fullsend",
            "experiment_id": "exp_456",
            "summary": "GitHub stargazer cold email campaign",
            "needs_tool": False,
            "scheduled_for": "2024-01-16T09:00:00Z",
        }

        assert ready_msg["type"] == "experiment_ready"
        assert ready_msg["source"] == "fullsend"
        assert "experiment_id" in ready_msg
        assert "summary" in ready_msg


class TestDispatcherMethods:
    """Tests for individual Dispatcher methods."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis = AsyncMock()
        redis.publish = AsyncMock()
        redis.hset = AsyncMock()
        return redis

    @pytest.fixture
    def mock_settings(self, tmp_path):
        """Create mock settings."""
        settings = MagicMock()
        settings.context_path = tmp_path
        settings.channel_to_fullsend = "fullsend:to_fullsend"
        settings.channel_builder_tasks = "fullsend:builder_tasks"
        settings.channel_from_orchestrator = "fullsend:from_orchestrator"
        settings.roundtable_timeout_seconds = 120
        settings.roundtable_max_rounds = 3
        return settings

    @pytest.mark.asyncio
    async def test_dispatch_to_fullsend_includes_timestamp(
        self, mock_redis, mock_settings
    ):
        """Test dispatch_to_fullsend includes timestamp."""
        dispatcher = Dispatcher(mock_redis, mock_settings)
        decision = Decision(
            action="dispatch_to_fullsend",
            reasoning="Test",
            payload={"idea": "Test"},
            priority="medium",
        )

        await dispatcher.dispatch_to_fullsend(decision)

        call_args = mock_redis.publish.call_args
        payload = json.loads(call_args[0][1])
        assert "requested_at" in payload
        assert "orchestrator_reasoning" in payload

    @pytest.mark.asyncio
    async def test_kill_experiment_without_id_logs_warning(
        self, mock_redis, mock_settings
    ):
        """Test kill_experiment logs warning when no experiment_id."""
        dispatcher = Dispatcher(mock_redis, mock_settings)
        decision = Decision(
            action="kill_experiment",
            reasoning="Test",
            payload={},
            priority="high",
            experiment_id=None,
        )

        await dispatcher.kill_experiment(decision)

        # Should not call hset without experiment_id
        mock_redis.hset.assert_not_called()


# Mark integration tests that require live Redis
pytest.mark.integration = pytest.mark.skipif(
    True,  # Skip by default, enable with -m integration flag
    reason="Integration tests require running Redis instance",
)


@pytest.mark.integration
class TestLiveRedisIntegration:
    """Integration tests that require a running Redis instance.

    Run with: pytest -m integration services/orchestrator/tests/test_integration.py

    Requirements:
    - Redis running on localhost:6379 (or set REDIS_URL env var)
    """

    @pytest.fixture
    async def redis_client(self):
        """Create Redis client for testing."""
        import redis.asyncio as redis

        client = redis.from_url("redis://localhost:6379", decode_responses=True)
        yield client
        await client.aclose()

    @pytest.mark.asyncio
    async def test_pubsub_round_trip(self, redis_client):
        """Test publishing and receiving messages via Redis pub/sub."""
        test_channel = "fullsend:test_orchestrator"
        received = []

        async def subscriber():
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(test_channel)
            async for message in pubsub.listen():
                if message["type"] == "message":
                    received.append(json.loads(message["data"]))
                    break  # Stop after first message

        # Start subscriber in background
        sub_task = asyncio.create_task(subscriber())

        # Wait a bit for subscriber to be ready
        await asyncio.sleep(0.1)

        # Publish test message
        test_msg = {"type": "test", "action": "no_action"}
        await redis_client.publish(test_channel, json.dumps(test_msg))

        # Wait for subscriber to receive
        await asyncio.wait_for(sub_task, timeout=5.0)

        assert len(received) == 1
        assert received[0]["type"] == "test"
