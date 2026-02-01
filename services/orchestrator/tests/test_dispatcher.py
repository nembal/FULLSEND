"""Unit tests for the dispatcher module."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.orchestrator.dispatcher import (
    Decision,
    Dispatcher,
    execute_decision,
)


class TestDispatcher:
    """Tests for Dispatcher class."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis = AsyncMock()
        redis.publish = AsyncMock(return_value=1)
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
        settings.roundtable_timeout_seconds = 10
        settings.roundtable_max_rounds = 2
        return settings

    @pytest.fixture
    def dispatcher(self, mock_redis, mock_settings):
        """Create Dispatcher instance."""
        return Dispatcher(mock_redis, mock_settings)


class TestDispatchToFullsend(TestDispatcher):
    """Tests for dispatch_to_fullsend method."""

    @pytest.mark.asyncio
    async def test_publishes_to_correct_channel(self, dispatcher, mock_redis):
        """Test publishes to fullsend:to_fullsend channel."""
        decision = Decision(
            action="dispatch_to_fullsend",
            reasoning="Good idea",
            payload={"idea": "Test scraping"},
            priority="high",
        )

        await dispatcher.dispatch_to_fullsend(decision)

        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        assert call_args[0][0] == "fullsend:to_fullsend"

    @pytest.mark.asyncio
    async def test_payload_format(self, dispatcher, mock_redis):
        """Test published payload matches PRD format."""
        decision = Decision(
            action="dispatch_to_fullsend",
            reasoning="Testing this idea",
            payload={"idea": "Scrape GitHub"},
            priority="high",
            context_for_fullsend="Use existing scraper tool",
        )

        await dispatcher.dispatch_to_fullsend(decision)

        published_data = json.loads(mock_redis.publish.call_args[0][1])
        assert published_data["type"] == "experiment_request"
        assert published_data["idea"] == {"idea": "Scrape GitHub"}
        assert published_data["context"] == "Use existing scraper tool"
        assert published_data["priority"] == "high"
        assert "requested_at" in published_data
        assert published_data["orchestrator_reasoning"] == "Testing this idea"


class TestDispatchToBuilder(TestDispatcher):
    """Tests for dispatch_to_builder method."""

    @pytest.mark.asyncio
    async def test_publishes_to_correct_channel(self, dispatcher, mock_redis):
        """Test publishes to fullsend:builder_tasks channel."""
        decision = Decision(
            action="dispatch_to_builder",
            reasoning="Need new tool",
            payload={"name": "scraper", "purpose": "Scrape data"},
            priority="medium",
        )

        await dispatcher.dispatch_to_builder(decision)

        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        assert call_args[0][0] == "fullsend:builder_tasks"

    @pytest.mark.asyncio
    async def test_payload_format(self, dispatcher, mock_redis):
        """Test published payload matches PRD format."""
        decision = Decision(
            action="dispatch_to_builder",
            reasoning="Need scraper tool",
            payload={"name": "github_scraper", "purpose": "Scrape stargazers"},
            priority="high",
        )

        await dispatcher.dispatch_to_builder(decision)

        published_data = json.loads(mock_redis.publish.call_args[0][1])
        assert published_data["type"] == "tool_prd"
        assert published_data["prd"]["name"] == "github_scraper"
        assert published_data["requested_by"] == "orchestrator"
        assert published_data["priority"] == "high"
        assert "requested_at" in published_data


class TestRespondToDiscord(TestDispatcher):
    """Tests for respond_to_discord method."""

    @pytest.mark.asyncio
    async def test_publishes_to_correct_channel(self, dispatcher, mock_redis):
        """Test publishes to fullsend:from_orchestrator channel."""
        decision = Decision(
            action="respond_to_discord",
            reasoning="Status query",
            payload={"content": "System is running"},
            priority="low",
        )
        original_msg = {"channel_id": "123", "message_id": "456"}

        await dispatcher.respond_to_discord(decision, original_msg)

        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        assert call_args[0][0] == "fullsend:from_orchestrator"

    @pytest.mark.asyncio
    async def test_payload_format(self, dispatcher, mock_redis):
        """Test published payload matches PRD format."""
        decision = Decision(
            action="respond_to_discord",
            reasoning="Status query",
            payload={"content": "Running 3 experiments"},
            priority="low",
        )
        original_msg = {"channel_id": "123", "message_id": "456"}

        await dispatcher.respond_to_discord(decision, original_msg)

        published_data = json.loads(mock_redis.publish.call_args[0][1])
        assert published_data["type"] == "orchestrator_response"
        assert published_data["channel_id"] == "123"
        assert published_data["content"] == "Running 3 experiments"
        assert published_data["reply_to"] == "456"
        assert published_data["priority"] == "low"


class TestKillExperiment(TestDispatcher):
    """Tests for kill_experiment method."""

    @pytest.mark.asyncio
    async def test_archives_experiment_in_redis(self, dispatcher, mock_redis):
        """Test sets experiment state to archived in Redis."""
        decision = Decision(
            action="kill_experiment",
            reasoning="Failing badly",
            payload={"reason": "Low response rate"},
            priority="high",
            experiment_id="exp_123",
        )

        await dispatcher.kill_experiment(decision)

        mock_redis.hset.assert_called_once()
        call_args = mock_redis.hset.call_args
        assert call_args[0][0] == "experiments:exp_123"
        assert call_args[1]["mapping"]["state"] == "archived"
        assert call_args[1]["mapping"]["archived_by"] == "orchestrator"
        assert "archived_at" in call_args[1]["mapping"]
        assert call_args[1]["mapping"]["archived_reason"] == "Low response rate"

    @pytest.mark.asyncio
    async def test_does_nothing_without_experiment_id(self, dispatcher, mock_redis):
        """Test does nothing if experiment_id is missing."""
        decision = Decision(
            action="kill_experiment",
            reasoning="Failing",
            payload={},
            priority="high",
        )

        await dispatcher.kill_experiment(decision)

        mock_redis.hset.assert_not_called()


class TestDoUpdateWorklist(TestDispatcher):
    """Tests for do_update_worklist method."""

    @pytest.mark.asyncio
    async def test_updates_worklist_file(self, dispatcher, mock_settings):
        """Test updates worklist.md file."""
        decision = Decision(
            action="update_worklist",
            reasoning="Priorities changed",
            payload={"content": "## New Worklist\n- Task 1"},
            priority="medium",
        )

        await dispatcher.do_update_worklist(decision)

        worklist_path = mock_settings.context_path / "worklist.md"
        assert worklist_path.exists()
        assert worklist_path.read_text() == "## New Worklist\n- Task 1"

    @pytest.mark.asyncio
    async def test_handles_string_payload(self, dispatcher, mock_settings):
        """Test handles string payload directly."""
        decision = Decision(
            action="update_worklist",
            reasoning="Priorities changed",
            payload="## Direct Worklist",  # type: ignore (testing flexibility)
            priority="medium",
        )
        # Force payload to be a string for test
        decision.payload = "## Direct Worklist"

        await dispatcher.do_update_worklist(decision)

        worklist_path = mock_settings.context_path / "worklist.md"
        assert worklist_path.read_text() == "## Direct Worklist"


class TestDoRecordLearning(TestDispatcher):
    """Tests for do_record_learning method."""

    @pytest.mark.asyncio
    async def test_appends_learning_to_file(self, dispatcher, mock_settings):
        """Test appends learning to learnings.md file."""
        # Create initial file
        learnings_path = mock_settings.context_path / "learnings.md"
        learnings_path.write_text("# Learnings")

        decision = Decision(
            action="record_learning",
            reasoning="New insight",
            payload={"learning": "Event targeting works!"},
            priority="low",
        )

        await dispatcher.do_record_learning(decision)

        content = learnings_path.read_text()
        assert "Event targeting works!" in content
        assert "## 20" in content  # Timestamp

    @pytest.mark.asyncio
    async def test_handles_different_payload_formats(self, dispatcher, mock_settings):
        """Test handles insight, content, and learning keys."""
        learnings_path = mock_settings.context_path / "learnings.md"
        learnings_path.write_text("")

        # Test with 'insight' key
        decision = Decision(
            action="record_learning",
            reasoning="New insight",
            payload={"insight": "CTOs respond better"},
            priority="low",
        )

        await dispatcher.do_record_learning(decision)

        content = learnings_path.read_text()
        assert "CTOs respond better" in content


class TestInitiateRoundtable(TestDispatcher):
    """Tests for initiate_roundtable method."""

    @pytest.mark.asyncio
    async def test_returns_error_without_prompt(self, dispatcher):
        """Test returns error dict if prompt is missing."""
        decision = Decision(
            action="initiate_roundtable",
            reasoning="Need ideas",
            payload={},
            priority="medium",
        )

        result = await dispatcher.initiate_roundtable(decision)

        assert "error" in result
        assert result["transcript"] == []
        assert result["summary"] == ""

    @pytest.mark.asyncio
    async def test_handles_subprocess_timeout(self, dispatcher):
        """Test handles subprocess timeout gracefully."""
        decision = Decision(
            action="initiate_roundtable",
            reasoning="Need debate",
            payload={"prompt": "What should we focus on?"},
            priority="medium",
        )

        with patch.object(dispatcher, "_run_roundtable_subprocess") as mock_run:
            import asyncio
            mock_run.side_effect = asyncio.TimeoutError("Subprocess timed out")

            result = await dispatcher.initiate_roundtable(decision)

            assert "error" in result
            assert "timed out" in result["error"]


class TestExecuteDecision:
    """Tests for execute_decision function."""

    @pytest.fixture
    def mock_dispatcher(self):
        """Create mock Dispatcher."""
        dispatcher = MagicMock()
        dispatcher.dispatch_to_fullsend = AsyncMock()
        dispatcher.dispatch_to_builder = AsyncMock()
        dispatcher.respond_to_discord = AsyncMock()
        dispatcher.kill_experiment = AsyncMock()
        dispatcher.do_update_worklist = AsyncMock()
        dispatcher.do_record_learning = AsyncMock()
        dispatcher.initiate_roundtable = AsyncMock(
            return_value={"transcript": [], "summary": ""}
        )
        return dispatcher

    @pytest.mark.asyncio
    async def test_routes_dispatch_to_fullsend(self, mock_dispatcher):
        """Test routes dispatch_to_fullsend to correct method."""
        decision = Decision(
            action="dispatch_to_fullsend",
            reasoning="Test",
            payload={"idea": "Test"},
            priority="high",
        )

        await execute_decision(decision, {}, mock_dispatcher)

        mock_dispatcher.dispatch_to_fullsend.assert_called_once_with(decision)

    @pytest.mark.asyncio
    async def test_routes_dispatch_to_builder(self, mock_dispatcher):
        """Test routes dispatch_to_builder to correct method."""
        decision = Decision(
            action="dispatch_to_builder",
            reasoning="Test",
            payload={"name": "tool"},
            priority="medium",
        )

        await execute_decision(decision, {}, mock_dispatcher)

        mock_dispatcher.dispatch_to_builder.assert_called_once_with(decision)

    @pytest.mark.asyncio
    async def test_routes_respond_to_discord(self, mock_dispatcher):
        """Test routes respond_to_discord to correct method."""
        decision = Decision(
            action="respond_to_discord",
            reasoning="Test",
            payload={"content": "Hello"},
            priority="low",
        )
        original_msg = {"channel_id": "123"}

        await execute_decision(decision, original_msg, mock_dispatcher)

        mock_dispatcher.respond_to_discord.assert_called_once_with(decision, original_msg)

    @pytest.mark.asyncio
    async def test_routes_update_worklist(self, mock_dispatcher):
        """Test routes update_worklist to correct method."""
        decision = Decision(
            action="update_worklist",
            reasoning="Test",
            payload={"content": "New worklist"},
            priority="medium",
        )

        await execute_decision(decision, {}, mock_dispatcher)

        mock_dispatcher.do_update_worklist.assert_called_once_with(decision)

    @pytest.mark.asyncio
    async def test_routes_record_learning(self, mock_dispatcher):
        """Test routes record_learning to correct method."""
        decision = Decision(
            action="record_learning",
            reasoning="Test",
            payload={"learning": "Insight"},
            priority="low",
        )

        await execute_decision(decision, {}, mock_dispatcher)

        mock_dispatcher.do_record_learning.assert_called_once_with(decision)

    @pytest.mark.asyncio
    async def test_routes_kill_experiment(self, mock_dispatcher):
        """Test routes kill_experiment to correct method."""
        decision = Decision(
            action="kill_experiment",
            reasoning="Test",
            payload={},
            priority="high",
            experiment_id="exp_123",
        )

        await execute_decision(decision, {}, mock_dispatcher)

        mock_dispatcher.kill_experiment.assert_called_once_with(decision)

    @pytest.mark.asyncio
    async def test_routes_initiate_roundtable(self, mock_dispatcher):
        """Test routes initiate_roundtable to correct method and returns result."""
        decision = Decision(
            action="initiate_roundtable",
            reasoning="Test",
            payload={"prompt": "What now?"},
            priority="medium",
        )

        result = await execute_decision(decision, {}, mock_dispatcher)

        mock_dispatcher.initiate_roundtable.assert_called_once_with(decision)
        assert result == {"transcript": [], "summary": ""}

    @pytest.mark.asyncio
    async def test_handles_no_action(self, mock_dispatcher):
        """Test handles no_action without calling any method."""
        decision = Decision(
            action="no_action",
            reasoning="Nothing to do",
            payload={},
            priority="low",
        )

        result = await execute_decision(decision, {}, mock_dispatcher)

        assert result is None
        # Verify no dispatcher methods were called
        mock_dispatcher.dispatch_to_fullsend.assert_not_called()
        mock_dispatcher.dispatch_to_builder.assert_not_called()
        mock_dispatcher.respond_to_discord.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_unknown_action(self, mock_dispatcher):
        """Test handles unknown action gracefully."""
        decision = Decision(
            action="unknown_action",  # type: ignore (testing edge case)
            reasoning="Test",
            payload={},
            priority="low",
        )
        # Force unknown action
        decision.action = "unknown_action"

        result = await execute_decision(decision, {}, mock_dispatcher)

        assert result is None
