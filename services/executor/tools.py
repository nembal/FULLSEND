"""
Anthropic tool definitions for the executor (Browserbase + Stagehand).
Forms: use browser_act with natural language (e.g. "fill the email field with X", "click Submit").
"""

from typing import Any

# Tool definitions for Claude (Anthropic Messages API)
EXECUTOR_TOOLS = [
    {
        "name": "browser_navigate",
        "description": "Navigate the browser to a URL.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "Full URL to open"}},
            "required": ["url"],
        },
    },
    {
        "name": "browser_act",
        "description": "Perform an action on the page using natural language. Use for clicks, form fills, and submissions (e.g. 'fill the email field with user@example.com', 'click the Submit button').",
        "input_schema": {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "Natural language instruction or JSON action from observe",
                }
            },
            "required": ["input"],
        },
    },
    {
        "name": "browser_extract",
        "description": "Extract data from the current page (e.g. page text, specific fields).",
        "input_schema": {
            "type": "object",
            "properties": {
                "instruction": {"type": "string", "description": "What to extract (e.g. 'extract the main heading and first paragraph')"},
                "schema": {"type": "object", "description": "Optional JSON schema for structured output"},
            },
            "required": ["instruction"],
        },
    },
    {
        "name": "browser_observe",
        "description": "Find actionable elements on the page (e.g. buttons, links, form fields). Returns a list of actions you can pass to browser_act.",
        "input_schema": {
            "type": "object",
            "properties": {
                "instruction": {"type": "string", "description": "What to find (e.g. 'find the login button and email input')"}
            },
            "required": ["instruction"],
        },
    },
    {
        "name": "browser_session_close",
        "description": "Close the browser session and free resources. Call when done with browser tasks.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


async def run_tool(
    name: str,
    arguments: dict[str, Any],
    session: Any,
) -> str:
    """
    Execute one tool by name. session is StagehandSession or None (browser unavailable).
    Returns a string result for Claude.
    """
    if session is None:
        return "Browser unavailable (missing BROWSERBASE_API_KEY, BROWSERBASE_PROJECT_ID, or MODEL_API_KEY)."

    if name == "browser_navigate":
        url = arguments.get("url", "")
        if not url:
            return "Missing url."
        out = await session.navigate(url=url)
        return _format_tool_result(out)

    if name == "browser_act":
        inp = arguments.get("input")
        if inp is None:
            return "Missing input."
        if isinstance(inp, dict):
            out = await session.act(input_spec=inp)
        else:
            out = await session.act(input_spec=str(inp))
        return _format_tool_result(out)

    if name == "browser_extract":
        instruction = arguments.get("instruction", "")
        schema = arguments.get("schema")
        if not instruction:
            return "Missing instruction."
        out = await session.extract(instruction=instruction, schema=schema)
        return _format_tool_result(out)

    if name == "browser_observe":
        instruction = arguments.get("instruction", "")
        if not instruction:
            return "Missing instruction."
        out = await session.observe(instruction=instruction)
        if out.get("ok") and out.get("actions"):
            return f"Actions: {out['actions']}"
        if not out.get("ok"):
            return f"Error: {out.get('error', 'unknown')}"
        return "No actions found."

    if name == "browser_session_close":
        await session.end()
        return "Session closed."

    return f"Unknown tool: {name}"


def _format_tool_result(out: dict[str, Any]) -> str:
    if out.get("ok"):
        msg = out.get("message") or out.get("data")
        return str(msg) if msg is not None else "ok"
    return f"Error: {out.get('error', 'unknown')}"
