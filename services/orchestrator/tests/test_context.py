"""Unit tests for the context module."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.orchestrator.context import (
    Context,
    append_learning,
    get_active_experiments,
    get_available_tools,
    get_recent_metrics,
    load_context,
    load_context_safe,
    read_file_safe,
    update_worklist,
    write_file,
)


class TestReadFileSafe:
    """Tests for read_file_safe function."""

    @pytest.mark.asyncio
    async def test_read_existing_file(self, tmp_path):
        """Test reading an existing file returns its content."""
        test_file = tmp_path / "test.md"
        test_file.write_text("Hello, World!")

        content = await read_file_safe(test_file)

        assert content == "Hello, World!"

    @pytest.mark.asyncio
    async def test_read_nonexistent_file_returns_empty_string(self, tmp_path):
        """Test reading a nonexistent file returns empty string."""
        nonexistent = tmp_path / "does_not_exist.md"

        content = await read_file_safe(nonexistent)

        assert content == ""

    @pytest.mark.asyncio
    async def test_read_empty_file(self, tmp_path):
        """Test reading an empty file returns empty string."""
        empty_file = tmp_path / "empty.md"
        empty_file.write_text("")

        content = await read_file_safe(empty_file)

        assert content == ""


class TestWriteFile:
    """Tests for write_file function."""

    @pytest.mark.asyncio
    async def test_write_creates_file(self, tmp_path):
        """Test write creates a new file with content."""
        test_file = tmp_path / "new_file.md"

        await write_file(test_file, "Test content")

        assert test_file.exists()
        assert test_file.read_text() == "Test content"

    @pytest.mark.asyncio
    async def test_write_overwrites_existing_file(self, tmp_path):
        """Test write overwrites existing file content."""
        test_file = tmp_path / "existing.md"
        test_file.write_text("Old content")

        await write_file(test_file, "New content")

        assert test_file.read_text() == "New content"

    @pytest.mark.asyncio
    async def test_write_creates_parent_directories(self, tmp_path):
        """Test write creates parent directories if they don't exist."""
        nested_file = tmp_path / "deep" / "nested" / "file.md"

        await write_file(nested_file, "Nested content")

        assert nested_file.exists()
        assert nested_file.read_text() == "Nested content"


class TestGetActiveExperiments:
    """Tests for get_active_experiments function."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_experiments(self):
        """Test returns empty list when Redis has no experiments."""
        mock_redis = AsyncMock()
        mock_redis.scan.return_value = (0, [])

        experiments = await get_active_experiments(mock_redis)

        assert experiments == []

    @pytest.mark.asyncio
    async def test_returns_active_experiments(self):
        """Test returns only non-archived experiments."""
        mock_redis = AsyncMock()
        mock_redis.scan.return_value = (0, [b"experiments:exp_1", b"experiments:exp_2"])
        mock_redis.hgetall.side_effect = [
            {b"id": b"exp_1", b"name": b"Test 1", b"state": b"active"},
            {b"id": b"exp_2", b"name": b"Test 2", b"state": b"archived"},
        ]

        experiments = await get_active_experiments(mock_redis)

        assert len(experiments) == 1
        assert experiments[0]["id"] == "exp_1"
        assert experiments[0]["state"] == "active"

    @pytest.mark.asyncio
    async def test_handles_redis_error_gracefully(self):
        """Test returns empty list on Redis error."""
        mock_redis = AsyncMock()
        mock_redis.scan.side_effect = Exception("Redis connection error")

        experiments = await get_active_experiments(mock_redis)

        assert experiments == []


class TestGetAvailableTools:
    """Tests for get_available_tools function."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_tools(self):
        """Test returns empty list when Redis has no tools."""
        mock_redis = AsyncMock()
        mock_redis.scan.return_value = (0, [])

        tools = await get_available_tools(mock_redis)

        assert tools == []

    @pytest.mark.asyncio
    async def test_returns_active_tools(self):
        """Test returns only active tools."""
        mock_redis = AsyncMock()
        mock_redis.scan.return_value = (0, [b"tools:scraper", b"tools:sender"])
        mock_redis.hgetall.side_effect = [
            {b"name": b"scraper", b"state": b"active"},
            {b"name": b"sender", b"state": b"inactive"},
        ]

        tools = await get_available_tools(mock_redis)

        assert len(tools) == 1
        assert tools[0] == "scraper"

    @pytest.mark.asyncio
    async def test_extracts_name_from_key_if_missing(self):
        """Test extracts tool name from key if name field is missing."""
        mock_redis = AsyncMock()
        mock_redis.scan.return_value = (0, [b"tools:my_tool"])
        mock_redis.hgetall.return_value = {b"state": b"active"}

        tools = await get_available_tools(mock_redis)

        assert len(tools) == 1
        assert tools[0] == "my_tool"

    @pytest.mark.asyncio
    async def test_handles_redis_error_gracefully(self):
        """Test returns empty list on Redis error."""
        mock_redis = AsyncMock()
        mock_redis.scan.side_effect = Exception("Redis connection error")

        tools = await get_available_tools(mock_redis)

        assert tools == []


class TestGetRecentMetrics:
    """Tests for get_recent_metrics function."""

    @pytest.mark.asyncio
    async def test_returns_empty_dict_when_no_metrics(self):
        """Test returns empty dict when Redis has no metrics."""
        mock_redis = AsyncMock()
        mock_redis.scan.return_value = (0, [])

        metrics = await get_recent_metrics(mock_redis)

        assert metrics == {}

    @pytest.mark.asyncio
    async def test_reads_timeseries_metrics(self):
        """Test reads metrics from Redis TimeSeries."""
        mock_redis = AsyncMock()
        mock_redis.scan.return_value = (0, [b"metrics_aggregated:exp_1"])
        mock_redis.execute_command.return_value = (1704067200000, 0.15)

        metrics = await get_recent_metrics(mock_redis)

        assert "exp_1" in metrics
        assert metrics["exp_1"]["timestamp"] == 1704067200000
        assert metrics["exp_1"]["value"] == 0.15

    @pytest.mark.asyncio
    async def test_falls_back_to_hash_on_timeseries_error(self):
        """Test falls back to Hash read if TimeSeries command fails."""
        mock_redis = AsyncMock()
        mock_redis.scan.return_value = (0, [b"metrics_aggregated:exp_1"])
        mock_redis.execute_command.side_effect = Exception("TimeSeries not available")
        mock_redis.hgetall.return_value = {b"response_rate": b"0.12"}

        metrics = await get_recent_metrics(mock_redis)

        assert "exp_1" in metrics
        assert metrics["exp_1"]["response_rate"] == "0.12"


class TestLoadContext:
    """Tests for load_context function."""

    @pytest.fixture
    def mock_settings(self, tmp_path):
        """Create mock settings with temp context path."""
        settings = MagicMock()
        settings.context_path = tmp_path
        return settings

    @pytest.fixture
    def setup_context_files(self, mock_settings):
        """Create context files for testing."""
        context_path = mock_settings.context_path
        (context_path / "product_context.md").write_text("# Test Product")
        (context_path / "worklist.md").write_text("## Worklist\n- Task 1")
        (context_path / "learnings.md").write_text("## Learnings\n- Insight 1")

    @pytest.mark.asyncio
    async def test_load_context_reads_all_files(self, mock_settings, setup_context_files):
        """Test load_context reads all context files."""
        mock_redis = AsyncMock()
        mock_redis.scan.return_value = (0, [])

        context = await load_context(mock_redis, mock_settings)

        assert context.product == "# Test Product"
        assert "Worklist" in context.worklist
        assert "Learnings" in context.learnings

    @pytest.mark.asyncio
    async def test_load_context_handles_missing_files(self, mock_settings):
        """Test load_context handles missing files gracefully."""
        mock_redis = AsyncMock()
        mock_redis.scan.return_value = (0, [])

        context = await load_context(mock_redis, mock_settings)

        assert context.product == ""
        assert context.worklist == ""
        assert context.learnings == ""


class TestLoadContextSafe:
    """Tests for load_context_safe function."""

    @pytest.fixture
    def mock_settings(self, tmp_path):
        """Create mock settings with temp context path."""
        settings = MagicMock()
        settings.context_path = tmp_path
        return settings

    @pytest.mark.asyncio
    async def test_returns_empty_context_on_error(self, mock_settings):
        """Test returns empty Context on any error."""
        mock_redis = AsyncMock()
        mock_redis.scan.side_effect = Exception("Redis error")

        context = await load_context_safe(mock_redis, mock_settings)

        assert isinstance(context, Context)
        assert context.product == ""
        assert context.worklist == ""
        assert context.learnings == ""
        assert context.active_experiments == []
        assert context.available_tools == []
        assert context.recent_metrics == {}


class TestUpdateWorklist:
    """Tests for update_worklist function."""

    @pytest.fixture
    def mock_settings(self, tmp_path):
        """Create mock settings with temp context path."""
        settings = MagicMock()
        settings.context_path = tmp_path
        return settings

    @pytest.mark.asyncio
    async def test_updates_worklist_file(self, mock_settings):
        """Test update_worklist writes content to worklist.md."""
        new_content = "## Updated Worklist\n- New Task"

        await update_worklist(new_content, mock_settings)

        worklist_path = mock_settings.context_path / "worklist.md"
        assert worklist_path.exists()
        assert worklist_path.read_text() == new_content


class TestAppendLearning:
    """Tests for append_learning function."""

    @pytest.fixture
    def mock_settings(self, tmp_path):
        """Create mock settings with temp context path."""
        settings = MagicMock()
        settings.context_path = tmp_path
        return settings

    @pytest.mark.asyncio
    async def test_appends_learning_with_timestamp(self, mock_settings):
        """Test append_learning adds timestamped learning entry."""
        # Create initial learnings file
        learnings_path = mock_settings.context_path / "learnings.md"
        learnings_path.write_text("# Learnings")

        await append_learning("Event targeting works!", mock_settings)

        content = learnings_path.read_text()
        assert "# Learnings" in content
        assert "Event targeting works!" in content
        # Check timestamp header pattern
        assert "## 20" in content  # Timestamp starts with year

    @pytest.mark.asyncio
    async def test_creates_file_if_missing(self, mock_settings):
        """Test append_learning creates file if it doesn't exist."""
        await append_learning("First learning", mock_settings)

        learnings_path = mock_settings.context_path / "learnings.md"
        assert learnings_path.exists()
        assert "First learning" in learnings_path.read_text()


class TestContextDataclass:
    """Tests for Context dataclass."""

    def test_context_creation_with_all_fields(self):
        """Test Context can be created with all fields."""
        context = Context(
            product="Test product",
            worklist="Test worklist",
            learnings="Test learnings",
            active_experiments=[{"id": "exp_1", "name": "Test"}],
            available_tools=["scraper", "sender"],
            recent_metrics={"exp_1": {"rate": 0.15}},
        )

        assert context.product == "Test product"
        assert context.worklist == "Test worklist"
        assert context.learnings == "Test learnings"
        assert len(context.active_experiments) == 1
        assert len(context.available_tools) == 2
        assert "exp_1" in context.recent_metrics

    def test_context_empty_defaults(self):
        """Test Context can be created with empty values."""
        context = Context(
            product="",
            worklist="",
            learnings="",
            active_experiments=[],
            available_tools=[],
            recent_metrics={},
        )

        assert context.product == ""
        assert context.active_experiments == []
        assert context.recent_metrics == {}
