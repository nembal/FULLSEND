"""
Executor = launcher: spawn Claude Code CLI with task context and MCP.
No custom agent loop — Claude Code does its own orchestration and uses
user-configured MCP (e.g. Browserbase) and tools.
"""

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv

# Load .env from project root (parent of services/) so it works regardless of cwd
_project_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(_project_root / ".env")

from .config import (
    get_claude_cli_path,
    get_executor_allowed_tools,
    get_executor_system_prompt,
)

logger = logging.getLogger(__name__)


def build_prompt(task: str, context: str | None = None, steps: Sequence[str] | None = None) -> str:
    """Build the prompt we pass to Claude Code (-p)."""
    parts = []
    if context:
        parts.append(f"GTM task / context:\n{context.strip()}\n")
    parts.append(task.strip())
    if steps:
        step_lines = [f"  {i}. {s}" for i, s in enumerate(steps, 1)]
        parts.append("\nSteps to carry out:\n" + "\n".join(step_lines))
    return "\n".join(parts).strip()


def run(
    task: str,
    context: str | None = None,
    steps: Sequence[str] | None = None,
    *,
    output_format: str = "json",
    timeout: int | None = 300,
) -> str:
    """
    Spawn Claude Code CLI with the given task (and optional context/steps).
    Uses MCP and tools already configured in Claude Code (e.g. Browserbase).
    Returns the result text; on CLI failure returns an error message string.
    """
    claude_bin = get_claude_cli_path()
    if not claude_bin:
        return (
            "Executor: Claude Code CLI not found. Install it (e.g. npm install -g @anthropic-ai/claude-code)"
            " and configure MCP (e.g. Browserbase) in Claude Code. No custom orchestration — we just spawn the CLI."
        )

    prompt = build_prompt(task, context=context, steps=steps)
    allowed = get_executor_allowed_tools()
    # Default for headless: auto-approve common tools so we don't block on "grant me access to WebFetch"
    if not allowed:
        allowed = "Read,Edit,Bash,WebFetch"
    system = get_executor_system_prompt()

    cmd: list[str] = [claude_bin, "-p", prompt]
    if output_format:
        cmd.extend(["--output-format", output_format])
    if allowed:
        cmd.extend(["--allowedTools", allowed])
    if system:
        cmd.extend(["--append-system-prompt", system])

    env = os.environ.copy()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=_project_root,  # repo root so Claude sees .mcp.json and env is consistent
            env=env,
        )
    except subprocess.TimeoutExpired:
        return "Executor: Claude Code CLI timed out."
    except FileNotFoundError:
        return f"Executor: Claude Code CLI not found at: {claude_bin}"
    except Exception as e:
        logger.exception("Claude Code CLI failed: %s", e)
        return f"Executor: Claude Code CLI failed: {e}"

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip() or f"exit code {result.returncode}"
        return f"Executor: Claude Code CLI error: {err}"

    out = (result.stdout or "").strip()
    if output_format == "json" and out:
        try:
            data = json.loads(out)
            if isinstance(data.get("result"), str):
                return data["result"]
            if isinstance(data.get("structured_output"), (dict, list, str)):
                return str(data["structured_output"])
            return out
        except json.JSONDecodeError:
            pass
    return out
