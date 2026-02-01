"""Unit tests for the responder module."""

import pytest

from services.watcher.responder import format_recent_activity


class TestFormatRecentActivity:
    """Tests for format_recent_activity function."""

    def test_empty_list_returns_no_activity(self):
        """Test that empty list returns 'No recent activity'."""
        result = format_recent_activity([])
        assert result == "No recent activity"

    def test_none_list_returns_no_activity(self):
        """Test that None list (if passed) returns 'No recent activity'."""
        result = format_recent_activity(None)  # type: ignore
        assert result == "No recent activity"

    def test_plain_string_entries(self):
        """Test formatting plain string entries."""
        entries = ["Task completed", "Experiment started", "Results analyzed"]
        result = format_recent_activity(entries)

        assert "- Task completed" in result
        assert "- Experiment started" in result
        assert "- Results analyzed" in result

    def test_json_entries_with_summary(self):
        """Test formatting JSON entries with summary field."""
        entries = [
            '{"summary": "Completed LinkedIn scrape", "type": "experiment_complete"}',
            '{"summary": "Started new A/B test", "type": "experiment_start"}',
        ]
        result = format_recent_activity(entries)

        assert "- Completed LinkedIn scrape" in result
        assert "- Started new A/B test" in result

    def test_json_entries_with_type_fallback(self):
        """Test that JSON entries without summary use type field."""
        entries = [
            '{"type": "system_check", "timestamp": "2024-01-15T10:00:00Z"}',
        ]
        result = format_recent_activity(entries)

        assert "- system_check" in result

    def test_json_entries_mixed_formats(self):
        """Test handling mixed entry formats."""
        entries = [
            '{"summary": "First task"}',
            "Plain text entry",
            '{"type": "third_task"}',
        ]
        result = format_recent_activity(entries)

        assert "- First task" in result
        assert "- Plain text entry" in result
        assert "- third_task" in result

    def test_limits_to_three_entries(self):
        """Test that output is limited to 3 most recent entries."""
        entries = ["Entry 1", "Entry 2", "Entry 3", "Entry 4", "Entry 5"]
        result = format_recent_activity(entries)

        assert "- Entry 1" in result
        assert "- Entry 2" in result
        assert "- Entry 3" in result
        assert "Entry 4" not in result
        assert "Entry 5" not in result

    def test_handles_invalid_json(self):
        """Test graceful handling of invalid JSON strings."""
        entries = [
            '{"summary": "Valid entry"}',
            '{invalid json',
            "Plain text",
        ]
        result = format_recent_activity(entries)

        assert "- Valid entry" in result
        assert "- {invalid json" in result
        assert "- Plain text" in result

    def test_entries_separated_by_newlines(self):
        """Test that entries are separated by newlines."""
        entries = ["Entry 1", "Entry 2"]
        result = format_recent_activity(entries)

        lines = result.split("\n")
        assert len(lines) == 2
        assert lines[0] == "- Entry 1"
        assert lines[1] == "- Entry 2"


class TestGetSystemStatus:
    """Tests for get_system_status function.

    These tests use mocked Redis client to avoid requiring a live Redis instance.
    """

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        from unittest.mock import AsyncMock, MagicMock

        redis_client = AsyncMock()
        return redis_client

    @pytest.mark.asyncio
    async def test_returns_status_running(self, mock_redis):
        """Test reading 'running' status from Redis."""
        from services.watcher.responder import get_system_status

        mock_redis.get.return_value = "running"
        mock_redis.keys.return_value = []
        mock_redis.lrange.return_value = []

        result = await get_system_status(mock_redis)

        assert result["status"] == "running"
        mock_redis.get.assert_called_with("fullsend:status")

    @pytest.mark.asyncio
    async def test_returns_status_paused(self, mock_redis):
        """Test reading 'paused' status from Redis."""
        from services.watcher.responder import get_system_status

        mock_redis.get.return_value = "paused"
        mock_redis.keys.return_value = []
        mock_redis.lrange.return_value = []

        result = await get_system_status(mock_redis)

        assert result["status"] == "paused"

    @pytest.mark.asyncio
    async def test_returns_unknown_when_status_missing(self, mock_redis):
        """Test that missing status returns 'unknown'."""
        from services.watcher.responder import get_system_status

        mock_redis.get.return_value = None
        mock_redis.keys.return_value = []
        mock_redis.lrange.return_value = []

        result = await get_system_status(mock_redis)

        assert result["status"] == "unknown"

    @pytest.mark.asyncio
    async def test_counts_experiments(self, mock_redis):
        """Test counting total and active experiments."""
        from services.watcher.responder import get_system_status

        mock_redis.get.return_value = "running"
        mock_redis.keys.return_value = ["experiments:exp1", "experiments:exp2", "experiments:exp3"]
        mock_redis.type.return_value = "hash"
        mock_redis.hget.side_effect = ["running", "completed", "running"]
        mock_redis.lrange.return_value = []

        result = await get_system_status(mock_redis)

        assert result["total_experiments"] == 3
        assert result["active_experiments"] == 2

    @pytest.mark.asyncio
    async def test_gets_recent_runs(self, mock_redis):
        """Test retrieving recent activity."""
        from services.watcher.responder import get_system_status

        mock_redis.get.return_value = "running"
        mock_redis.keys.return_value = []
        mock_redis.lrange.return_value = ["activity1", "activity2"]

        result = await get_system_status(mock_redis)

        assert result["recent_runs"] == ["activity1", "activity2"]
        mock_redis.lrange.assert_called_with("fullsend:recent_runs", 0, 4)

    @pytest.mark.asyncio
    async def test_handles_redis_error(self, mock_redis):
        """Test graceful handling of Redis errors."""
        from services.watcher.responder import get_system_status

        mock_redis.get.side_effect = Exception("Connection error")

        result = await get_system_status(mock_redis)

        assert "error" in result
        assert "Connection error" in result["error"]

    @pytest.mark.asyncio
    async def test_skips_non_hash_keys(self, mock_redis):
        """Test that non-hash keys are skipped when counting experiments."""
        from services.watcher.responder import get_system_status

        mock_redis.get.return_value = "running"
        mock_redis.keys.return_value = ["experiments:exp1", "experiments:exp2"]
        mock_redis.type.side_effect = ["hash", "string"]  # exp2 is not a hash
        mock_redis.hget.return_value = "running"
        mock_redis.lrange.return_value = []

        result = await get_system_status(mock_redis)

        assert result["total_experiments"] == 1  # Only exp1 is a hash
        assert result["active_experiments"] == 1
