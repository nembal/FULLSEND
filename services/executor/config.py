"""
Executor config: Claude Code CLI path, allowed tools, optional system prompt.
MCP (e.g. Browserbase) is configured in Claude Code itself — we only spawn the CLI.
"""

import os
import shutil

from dotenv import load_dotenv

load_dotenv()


def get_claude_cli_path() -> str | None:
    """Path to Claude Code CLI. Default: CLAUDE_CLI_PATH env or 'claude' in PATH."""
    path = os.getenv("CLAUDE_CLI_PATH", "").strip()
    if path and os.path.isfile(path):
        return path
    if path and shutil.which(path):
        return path
    return shutil.which("claude")


def get_executor_allowed_tools() -> str | None:
    """
    Comma-separated tools to auto-approve for Claude Code (e.g. Read,Edit,Bash).
    MCP tools use their server names. Empty = use Claude Code defaults / prompts.
    """
    return (os.getenv("EXECUTOR_ALLOWED_TOOLS") or "").strip() or None


def get_executor_system_prompt() -> str | None:
    """Optional extra system prompt (--append-system-prompt)."""
    return (os.getenv("EXECUTOR_SYSTEM_PROMPT") or "").strip() or None
