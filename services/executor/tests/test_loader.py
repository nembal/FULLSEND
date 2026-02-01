"""Unit tests for the loader module.

Tests dynamic tool loading with:
- Loading tool by matching function name
- Loading tool with 'run' fallback
- ToolNotFoundError for missing tools
- ToolError for tools without callable functions
"""

import tempfile
from pathlib import Path

import pytest

from services.executor.loader import (
    ToolError,
    ToolNotFoundError,
    load_tool,
)


class TestLoadTool:
    """Tests for load_tool function."""

    def test_load_tool_matching_function_name(self, tmp_path: Path):
        """Test loading a tool with function matching filename."""
        tool_file = tmp_path / "sample_tool.py"
        tool_file.write_text(
            '''
def sample_tool(param1: str, param2: int = 10) -> dict:
    """A sample tool for testing."""
    return {"param1": param1, "param2": param2, "status": "ok"}
'''
        )

        tool_fn = load_tool("sample_tool", str(tmp_path))
        result = tool_fn(param1="test", param2=5)

        assert result["param1"] == "test"
        assert result["param2"] == 5
        assert result["status"] == "ok"

    def test_load_tool_run_fallback(self, tmp_path: Path):
        """Test loading a tool using 'run' function fallback."""
        tool_file = tmp_path / "other_tool.py"
        tool_file.write_text(
            '''
def run(value: str) -> dict:
    """Run function as fallback."""
    return {"value": value, "success": True}
'''
        )

        tool_fn = load_tool("other_tool", str(tmp_path))
        result = tool_fn(value="hello")

        assert result["value"] == "hello"
        assert result["success"] is True

    def test_load_tool_not_found_error(self, tmp_path: Path):
        """Test ToolNotFoundError for missing tool file."""
        with pytest.raises(ToolNotFoundError) as exc_info:
            load_tool("nonexistent_tool", str(tmp_path))

        assert "Tool not found: nonexistent_tool" in str(exc_info.value)

    def test_load_tool_no_callable_error(self, tmp_path: Path):
        """Test ToolError for tool without callable function."""
        tool_file = tmp_path / "empty_tool.py"
        tool_file.write_text(
            '''
# This tool has no callable function
SOME_CONSTANT = 42
'''
        )

        with pytest.raises(ToolError) as exc_info:
            load_tool("empty_tool", str(tmp_path))

        assert "has no callable function" in str(exc_info.value)

    def test_load_tool_prefers_matching_name_over_run(self, tmp_path: Path):
        """Test that matching function name takes precedence over run."""
        tool_file = tmp_path / "priority_tool.py"
        tool_file.write_text(
            '''
def priority_tool() -> str:
    """Named function takes priority."""
    return "from_named"

def run() -> str:
    """Fallback function."""
    return "from_run"
'''
        )

        tool_fn = load_tool("priority_tool", str(tmp_path))
        result = tool_fn()

        assert result == "from_named"

    def test_load_tool_with_imports(self, tmp_path: Path):
        """Test loading a tool that imports standard library modules."""
        tool_file = tmp_path / "import_tool.py"
        tool_file.write_text(
            '''
import json
import os

def import_tool(data: dict) -> str:
    """Tool that uses imports."""
    return json.dumps(data)
'''
        )

        tool_fn = load_tool("import_tool", str(tmp_path))
        result = tool_fn(data={"key": "value"})

        assert result == '{"key": "value"}'

    def test_load_tool_returns_list(self, tmp_path: Path):
        """Test loading a tool that returns a list."""
        tool_file = tmp_path / "list_tool.py"
        tool_file.write_text(
            '''
def list_tool(count: int) -> list:
    """Tool that returns a list."""
    return [{"id": i} for i in range(count)]
'''
        )

        tool_fn = load_tool("list_tool", str(tmp_path))
        result = tool_fn(count=3)

        assert len(result) == 3
        assert result[0]["id"] == 0
        assert result[2]["id"] == 2

    def test_load_tool_raises_exception(self, tmp_path: Path):
        """Test loading a tool that raises an exception when called."""
        tool_file = tmp_path / "error_tool.py"
        tool_file.write_text(
            '''
def error_tool() -> dict:
    """Tool that raises an error."""
    raise ValueError("Something went wrong")
'''
        )

        tool_fn = load_tool("error_tool", str(tmp_path))

        with pytest.raises(ValueError) as exc_info:
            tool_fn()

        assert "Something went wrong" in str(exc_info.value)
