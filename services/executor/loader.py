"""Dynamic tool loading from the tools directory."""

import importlib.util
import logging
from pathlib import Path
from typing import Any, Callable

import redis.asyncio as redis

from .config import get_settings

logger = logging.getLogger(__name__)


class ToolError(Exception):
    """Base exception for tool-related errors."""

    pass


class ToolNotFoundError(ToolError):
    """Raised when a tool cannot be found."""

    pass


class ToolTimeoutError(ToolError):
    """Raised when a tool execution exceeds timeout."""

    pass


class ToolRetryExhaustedError(ToolError):
    """Raised when all retry attempts for transient failures are exhausted."""

    def __init__(self, message: str, last_error: Exception, attempts: int):
        super().__init__(message)
        self.last_error = last_error
        self.attempts = attempts


def load_tool(tool_name: str, tools_path: str | None = None) -> Callable[..., Any]:
    """Dynamically load a tool from the tools directory.

    Args:
        tool_name: Name of the tool (without .py extension)
        tools_path: Path to tools directory (uses config default if None)

    Returns:
        Callable function from the tool module

    Raises:
        ToolNotFoundError: If tool file doesn't exist
        ToolError: If tool has no callable function
    """
    if tools_path is None:
        tools_path = get_settings().tools_path

    tool_path = Path(tools_path) / f"{tool_name}.py"

    if not tool_path.exists():
        raise ToolNotFoundError(f"Tool not found: {tool_name} (looked in {tool_path})")

    # Load the module
    spec = importlib.util.spec_from_file_location(tool_name, tool_path)
    if spec is None or spec.loader is None:
        raise ToolError(f"Failed to load tool spec: {tool_name}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Get the main function (convention: same name as file)
    if hasattr(module, tool_name):
        return getattr(module, tool_name)

    # Try 'run' as fallback
    if hasattr(module, "run"):
        logger.info(f"Tool {tool_name} using 'run' fallback function")
        return module.run

    raise ToolError(f"Tool {tool_name} has no callable function (expected '{tool_name}' or 'run')")


async def get_tool_metadata(tool_name: str, redis_client: redis.Redis) -> dict[str, Any]:
    """Get tool metadata from Redis registry.

    Args:
        tool_name: Name of the tool
        redis_client: Redis client instance

    Returns:
        Dictionary of tool metadata
    """
    metadata = await redis_client.hgetall(f"tools:{tool_name}")
    return metadata or {}
