"""Integration tests for the Executor service.

Tests end-to-end execution flows with mocked Redis:
- Full experiment execution with tool loading
- Metrics emission during execution
- Error handling (tool not found, tool errors, timeouts)
- State transitions in Redis
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.executor.config import Settings
from services.executor.loader import ToolNotFoundError
from services.executor.runner import execute_experiment


class TestFullExecutionFlow:
    """Integration tests for complete execution flow."""

    @pytest.fixture
    def tools_dir(self, tmp_path: Path):
        """Create a tools directory shared by all fixtures in a test."""
        return tmp_path

    @pytest.fixture
    def mock_settings(self, tools_dir: Path):
        """Create mock settings with temp tools path."""
        return Settings(
            tools_path=str(tools_dir),
            tool_execution_timeout=10,
            retry_max_attempts=2,
            retry_backoff_min=0.1,
            retry_backoff_max=1.0,
        )

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis = AsyncMock()
        redis.hset = AsyncMock()
        redis.publish = AsyncMock()
        redis.rpush = AsyncMock()
        return redis

    @pytest.fixture
    def sample_tool(self, tools_dir: Path):
        """Create a sample tool for testing."""
        tool_file = tools_dir / "test_tool.py"
        tool_file.write_text(
            '''
def test_tool(message: str = "hello") -> dict:
    """Sample test tool."""
    return {"message": message, "status": "success", "items": [1, 2, 3]}
'''
        )
        return tool_file

    @pytest.mark.asyncio
    async def test_successful_execution(
        self, mock_redis, mock_settings, sample_tool
    ):
        """Test successful experiment execution."""
        experiment = {
            "id": "exp_test_001",
            "tool": "test_tool",
            "params": '{"message": "hello world"}',
            "state": "ready",
        }

        await execute_experiment(mock_redis, experiment, mock_settings)

        # Verify state transitions: ready -> running -> run
        hset_calls = mock_redis.hset.call_args_list

        # Should have at least 3 hset calls:
        # 1. Set state to running
        # 2. Save run result
        # 3. Set state to run (completed)
        assert len(hset_calls) >= 2

        # First call sets state to running
        assert hset_calls[0][0][0] == "experiments:exp_test_001"
        assert hset_calls[0][0][1] == "state"
        assert hset_calls[0][0][2] == "running"

        # Verify completion was published
        publish_calls = mock_redis.publish.call_args_list
        # Should have metrics and result publishes
        assert len(publish_calls) >= 1

        # Find the experiment result publish
        result_publishes = [
            c for c in publish_calls
            if c[0][0] == "fullsend:experiment_results"
        ]
        assert len(result_publishes) >= 1

        result_data = json.loads(result_publishes[-1][0][1])
        assert result_data["type"] == "experiment_completed"
        assert result_data["status"] == "success"

    @pytest.mark.asyncio
    async def test_tool_not_found_handling(self, mock_redis, mock_settings):
        """Test handling of missing tool."""
        experiment = {
            "id": "exp_missing_tool",
            "tool": "nonexistent_tool",
            "params": "{}",
            "state": "ready",
        }

        await execute_experiment(mock_redis, experiment, mock_settings)

        # Verify failure was recorded
        publish_calls = mock_redis.publish.call_args_list
        result_publishes = [
            c for c in publish_calls
            if c[0][0] == "fullsend:experiment_results"
        ]

        assert len(result_publishes) >= 1
        result_data = json.loads(result_publishes[-1][0][1])
        assert result_data["type"] == "experiment_failed"
        assert result_data["error_type"] == "ToolNotFoundError"

        # Verify state set to failed
        hset_calls = mock_redis.hset.call_args_list
        state_updates = [
            c for c in hset_calls
            if len(c[0]) >= 3 and c[0][1] == "state"
        ]
        # Last state update should be "failed"
        assert state_updates[-1][0][2] == "failed"

    @pytest.mark.asyncio
    async def test_tool_error_handling(self, mock_redis, mock_settings, tools_dir):
        """Test handling of tool that raises an error."""
        # Create a tool that raises an error
        tool_file = tools_dir / "error_tool.py"
        tool_file.write_text(
            '''
def error_tool() -> dict:
    """Tool that always fails."""
    raise RuntimeError("Something went wrong in the tool")
'''
        )

        experiment = {
            "id": "exp_error_test",
            "tool": "error_tool",
            "params": "{}",
            "state": "ready",
        }

        await execute_experiment(mock_redis, experiment, mock_settings)

        # Verify failure was published
        publish_calls = mock_redis.publish.call_args_list
        result_publishes = [
            c for c in publish_calls
            if c[0][0] == "fullsend:experiment_results"
        ]

        result_data = json.loads(result_publishes[-1][0][1])
        assert result_data["type"] == "experiment_failed"
        assert "RuntimeError" in result_data["error_type"]

    @pytest.mark.asyncio
    async def test_metrics_emission(self, mock_redis, mock_settings, sample_tool):
        """Test that metrics are emitted during execution."""
        experiment = {
            "id": "exp_metrics_test",
            "tool": "test_tool",
            "params": "{}",
            "state": "ready",
        }

        await execute_experiment(mock_redis, experiment, mock_settings)

        # Check metrics were published
        publish_calls = mock_redis.publish.call_args_list
        metrics_publishes = [
            c for c in publish_calls
            if c[0][0] == "fullsend:metrics"
        ]

        # Should have at least run_started and run_completed metrics
        assert len(metrics_publishes) >= 2

        events = [json.loads(c[0][1])["event"] for c in metrics_publishes]
        assert "run_started" in events
        assert "run_completed" in events

    @pytest.mark.asyncio
    async def test_items_processed_metric_for_list_result(
        self, mock_redis, mock_settings, tools_dir
    ):
        """Test that items_processed metric is emitted for list results."""
        # Create a tool that returns a list (not a dict)
        tool_file = tools_dir / "list_tool.py"
        tool_file.write_text(
            '''
def list_tool(count: int = 3) -> list:
    """Tool that returns a list of items."""
    return [{"id": i, "processed": True} for i in range(count)]
'''
        )

        experiment = {
            "id": "exp_list_test",
            "tool": "list_tool",
            "params": '{"count": 5}',
            "state": "ready",
        }

        await execute_experiment(mock_redis, experiment, mock_settings)

        # Check metrics were published
        publish_calls = mock_redis.publish.call_args_list
        metrics_publishes = [
            c for c in publish_calls
            if c[0][0] == "fullsend:metrics"
        ]

        events = [json.loads(c[0][1]) for c in metrics_publishes]
        event_types = [e["event"] for e in events]

        assert "run_started" in event_types
        assert "run_completed" in event_types
        assert "items_processed" in event_types

        # Verify the count in items_processed
        items_event = next(e for e in events if e["event"] == "items_processed")
        assert items_event["count"] == 5

    @pytest.mark.asyncio
    async def test_metrics_persisted_to_redis(
        self, mock_redis, mock_settings, sample_tool
    ):
        """Test that metrics are persisted to Redis list."""
        experiment = {
            "id": "exp_persist_test",
            "tool": "test_tool",
            "params": "{}",
            "state": "ready",
        }

        await execute_experiment(mock_redis, experiment, mock_settings)

        # Check rpush was called to persist metrics
        rpush_calls = mock_redis.rpush.call_args_list
        assert len(rpush_calls) >= 2

        # All calls should be to the metrics list for this experiment
        for call in rpush_calls:
            assert call[0][0] == "metrics:exp_persist_test"

    @pytest.mark.asyncio
    async def test_execution_json_format(
        self, mock_redis, mock_settings, sample_tool
    ):
        """Test experiment with execution field as JSON string."""
        experiment = {
            "id": "exp_json_exec",
            "execution": json.dumps({
                "tool": "test_tool",
                "params": {"message": "from json"}
            }),
            "state": "ready",
        }

        await execute_experiment(mock_redis, experiment, mock_settings)

        # Verify successful completion
        publish_calls = mock_redis.publish.call_args_list
        result_publishes = [
            c for c in publish_calls
            if c[0][0] == "fullsend:experiment_results"
        ]

        result_data = json.loads(result_publishes[-1][0][1])
        assert result_data["type"] == "experiment_completed"

    @pytest.mark.asyncio
    async def test_run_result_saved(self, mock_redis, mock_settings, sample_tool):
        """Test that run result is saved to Redis."""
        experiment = {
            "id": "exp_save_test",
            "tool": "test_tool",
            "params": "{}",
            "state": "ready",
        }

        await execute_experiment(mock_redis, experiment, mock_settings)

        # Find the hset call for run result
        hset_calls = mock_redis.hset.call_args_list
        run_result_calls = [
            c for c in hset_calls
            if c[0][0].startswith("experiment_runs:")
        ]

        assert len(run_result_calls) == 1
        mapping = run_result_calls[0][1]["mapping"]
        assert mapping["status"] == "completed"
        assert "duration_seconds" in mapping
        assert "result_summary" in mapping
        assert "timestamp" in mapping
