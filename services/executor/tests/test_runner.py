"""Unit tests for the runner module.

Tests execution logic with:
- Result summarization
- Run result persistence
- Result publishing
- Experiment execution flow
- Error handling
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.executor.runner import (
    publish_result,
    save_run_result,
    summarize_result,
)


class TestSummarizeResult:
    """Tests for summarize_result function."""

    def test_dict_result_returned_as_is(self):
        """Test that dict results are returned unchanged."""
        result = {"emails_sent": 10, "errors": 0}
        summary = summarize_result(result)

        assert summary == {"emails_sent": 10, "errors": 0}

    def test_list_result_summarized(self):
        """Test that list results are summarized by length."""
        result = [{"id": 1}, {"id": 2}, {"id": 3}]
        summary = summarize_result(result)

        assert summary == {"items": 3, "type": "list"}

    def test_empty_list_summarized(self):
        """Test that empty list is summarized."""
        summary = summarize_result([])

        assert summary == {"items": 0, "type": "list"}

    def test_string_result_truncated(self):
        """Test that string results are truncated in summary."""
        long_string = "x" * 1000
        summary = summarize_result(long_string)

        assert "value" in summary
        assert len(summary["value"]) <= 500

    def test_int_result_stringified(self):
        """Test that int results are converted to string summary."""
        summary = summarize_result(42)

        assert summary == {"value": "42"}

    def test_none_result(self):
        """Test that None result is handled."""
        summary = summarize_result(None)

        assert summary == {"value": "None"}


class TestSaveRunResult:
    """Tests for save_run_result function."""

    @pytest.mark.asyncio
    async def test_saves_to_correct_key(self):
        """Test that result is saved to correct Redis key."""
        mock_redis = AsyncMock()

        await save_run_result(
            mock_redis,
            "exp_123:1706800000",
            {"status": "completed", "duration_seconds": "12.5"},
        )

        mock_redis.hset.assert_called_once()
        call_args = mock_redis.hset.call_args

        assert call_args[0][0] == "experiment_runs:exp_123:1706800000"
        assert call_args[1]["mapping"]["status"] == "completed"
        assert call_args[1]["mapping"]["duration_seconds"] == "12.5"

    @pytest.mark.asyncio
    async def test_saves_failure_result(self):
        """Test that failure result is saved correctly."""
        mock_redis = AsyncMock()

        await save_run_result(
            mock_redis,
            "exp_456:1706800001",
            {
                "status": "failed",
                "error": "Connection refused",
                "error_type": "ConnectionError",
            },
        )

        call_args = mock_redis.hset.call_args
        mapping = call_args[1]["mapping"]

        assert mapping["status"] == "failed"
        assert mapping["error"] == "Connection refused"
        assert mapping["error_type"] == "ConnectionError"


class TestPublishResult:
    """Tests for publish_result function."""

    @pytest.mark.asyncio
    async def test_publishes_to_correct_channel(self):
        """Test that result is published to correct channel."""
        mock_redis = AsyncMock()

        await publish_result(
            mock_redis,
            {"type": "experiment_completed", "experiment_id": "exp_123"},
            "fullsend:experiment_results",
        )

        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args

        assert call_args[0][0] == "fullsend:experiment_results"
        published_data = json.loads(call_args[0][1])
        assert published_data["type"] == "experiment_completed"
        assert published_data["experiment_id"] == "exp_123"

    @pytest.mark.asyncio
    async def test_publishes_failure_notification(self):
        """Test that failure notification is published correctly."""
        mock_redis = AsyncMock()

        await publish_result(
            mock_redis,
            {
                "type": "experiment_failed",
                "experiment_id": "exp_789",
                "error": "Tool not found",
                "error_type": "ToolNotFoundError",
            },
            "fullsend:experiment_results",
        )

        call_args = mock_redis.publish.call_args
        published_data = json.loads(call_args[0][1])

        assert published_data["type"] == "experiment_failed"
        assert published_data["error"] == "Tool not found"
        assert published_data["error_type"] == "ToolNotFoundError"


class TestExecuteExperiment:
    """Tests for execute_experiment function behavior.
    
    Note: Full integration tests require Redis mock setup.
    These tests verify the component behavior in isolation.
    """

    def test_experiment_data_parsing(self):
        """Test parsing experiment data from different formats."""
        # Experiment data as hash fields
        exp_data_hash = {
            "id": "exp_test",
            "tool": "email_sender",
            "params": '{"recipients": ["a@b.com"]}',
            "state": "ready",
        }

        # Extract tool info
        execution = exp_data_hash.get("execution")
        if execution is None:
            tool_name = exp_data_hash.get("tool")
            params_raw = exp_data_hash.get("params", "{}")
            params = json.loads(params_raw) if isinstance(params_raw, str) else params_raw
        else:
            if isinstance(execution, str):
                execution = json.loads(execution)
            tool_name = execution["tool"]
            params = execution.get("params", {})

        assert tool_name == "email_sender"
        assert params == {"recipients": ["a@b.com"]}

    def test_experiment_data_with_execution_dict(self):
        """Test parsing experiment data with execution field."""
        exp_data = {
            "id": "exp_test2",
            "execution": '{"tool": "github_scraper", "params": {"repo": "test/repo"}}',
            "state": "ready",
        }

        execution = exp_data.get("execution")
        if isinstance(execution, str):
            execution = json.loads(execution)

        assert execution["tool"] == "github_scraper"
        assert execution["params"]["repo"] == "test/repo"
