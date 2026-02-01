# Executor = launcher for Claude Code CLI (context + MCP; no custom orchestration).

from .runner import build_prompt, run

__all__ = ["build_prompt", "run"]
