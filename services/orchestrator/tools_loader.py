"""
Load available downstream-agent tools from Redis (or config file) and optionally seed Redis.
Source of truth: available_tools.json; orchestrator reads from Redis at runtime.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
# Schema: tools:available (see docs/redis_and_queues_schema.md)
REDIS_TOOLS_KEY = os.getenv("REDIS_TOOLS_KEY", "tools:available")
REDIS_TASK_PREFIX = "task:"
REDIS_TASK_BLOCKED_SUFFIX = ":blocked"
REDIS_SKILLS_INDEX = "skills:index"
REDIS_SKILL_PREFIX = "skill:"


def _tools_json_path() -> Path:
    """Path to available_tools.json (next to this package)."""
    return Path(__file__).resolve().parent / "available_tools.json"


def load_tools_from_file() -> list[dict]:
    """Load tool list from config file. Returns list of {name, description, constraints}."""
    path = _tools_json_path()
    if not path.exists():
        logger.warning("Available tools file not found: %s", path)
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def get_redis_client(url: str | None = None):
    """Return a sync Redis client (for orchestrator daemon)."""
    import redis
    return redis.from_url(url or REDIS_URL, decode_responses=True)


def load_tools_from_redis() -> list[dict] | None:
    """Load tool list from Redis. Returns None if key missing or error."""
    try:
        r = get_redis_client()
        raw = r.get(REDIS_TOOLS_KEY)
        if raw is None:
            return None
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning("Failed to load tools from Redis: %s", e)
        return None


def seed_redis_from_file() -> list[dict]:
    """Load tools from file and write to Redis. Returns the tool list."""
    tools = load_tools_from_file()
    if not tools:
        return []
    try:
        r = get_redis_client()
        r.set(REDIS_TOOLS_KEY, json.dumps(tools))
        logger.info("Seeded Redis %s with %d tools from file", REDIS_TOOLS_KEY, len(tools))
    except Exception as e:
        logger.warning("Failed to seed Redis with tools: %s", e)
    return tools


def get_available_tools() -> list[dict]:
    """
    Get available tools for the orchestrator: from Redis if present, else from file (and seed Redis).
    Returns list of {name, description, constraints}.
    """
    tools = load_tools_from_redis()
    if tools is not None:
        return tools
    tools = load_tools_from_file()
    if tools:
        seed_redis_from_file()
    return tools


def format_tools_for_prompt(tools: list[dict]) -> str:
    """Format tool list as a string for the LLM prompt."""
    if not tools:
        return "No specific tools are configured; propose steps that could be executed by generic agents (browser, email, social, etc.)."
    lines = ["Available downstream agents/tools (only propose steps that these can carry out):"]
    for t in tools:
        name = t.get("name", "?")
        desc = t.get("description", "")
        constraints = t.get("constraints", "")
        lines.append(f"- {name}: {desc} Constraints: {constraints}")
    return "\n".join(lines)


def write_task_state(
    task_id: str,
    context: str,
    next_steps: list[str],
    blocked: list[dict],
    topic: str = "",
    order: int | None = None,
    redis_url: str | None = None,
) -> None:
    """
    Write phase-2 task state to Redis: task:{uuid} with context, previous_steps=[], next_steps, blocked, topic, order.
    topic/order allow requeueing the same task payload after builder adds tools.
    """
    key = f"{REDIS_TASK_PREFIX}{task_id}"
    payload = {
        "context": context,
        "previous_steps": [],
        "next_steps": next_steps,
        "blocked": blocked,
        "topic": topic,
        "order": order,
        "updated_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    try:
        r = get_redis_client(redis_url)
        r.set(key, json.dumps(payload))
        logger.debug("Wrote task state to Redis %s", key)
    except Exception as e:
        logger.warning("Failed to write task state to Redis %s: %s", key, e)


def write_blocked_only(task_id: str, blocked: list[dict], redis_url: str | None = None) -> None:
    """Write blocked tasks + reasons to Redis (task:{uuid}:blocked)."""
    if not blocked:
        return
    key = f"{REDIS_TASK_PREFIX}{task_id}{REDIS_TASK_BLOCKED_SUFFIX}"
    try:
        r = get_redis_client(redis_url)
        r.set(key, json.dumps(blocked))
        logger.debug("Wrote blocked list to Redis %s", key)
    except Exception as e:
        logger.warning("Failed to write blocked to Redis %s: %s", key, e)


def delete_task_state(task_id: str, redis_url: str | None = None) -> None:
    """Delete task:{uuid} and task:{uuid}:blocked from Redis (e.g. after blocked tasks are requeued)."""
    try:
        r = get_redis_client(redis_url)
        r.delete(f"{REDIS_TASK_PREFIX}{task_id}")
        r.delete(f"{REDIS_TASK_PREFIX}{task_id}{REDIS_TASK_BLOCKED_SUFFIX}")
        logger.debug("Deleted task state from Redis task:%s", task_id)
    except Exception as e:
        logger.warning("Failed to delete task state %s: %s", task_id, e)


# --- Skills (real-time loadable; builder adds here) ---

def list_skills(redis_url: str | None = None) -> list[str]:
    """Return list of skill IDs from Redis skills:index."""
    try:
        r = get_redis_client(redis_url)
        raw = r.get(REDIS_SKILLS_INDEX)
        if raw is None:
            return []
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning("Failed to list skills: %s", e)
        return []


def get_skill(skill_id: str, redis_url: str | None = None) -> dict | None:
    """Load one skill by ID. Returns { id, name, description, content, addresses_blocked?, updated_at } or None."""
    try:
        r = get_redis_client(redis_url)
        raw = r.get(f"{REDIS_SKILL_PREFIX}{skill_id}")
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.warning("Failed to get skill %s: %s", skill_id, e)
        return None


def register_skill(
    skill_id: str,
    name: str,
    description: str,
    content: str,
    addresses_blocked: list[dict] | None = None,
    redis_url: str | None = None,
) -> None:
    """
    Write a skill to Redis (skill:{id}) and add id to skills:index.
    Builder consumer calls this when it ships a new skill. Loadable in real time.
    """
    key = f"{REDIS_SKILL_PREFIX}{skill_id}"
    payload = {
        "id": skill_id,
        "name": name,
        "description": description,
        "content": content,
        "addresses_blocked": addresses_blocked or [],
        "updated_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    try:
        r = get_redis_client(redis_url)
        r.set(key, json.dumps(payload))
        ids = list_skills(redis_url)
        if skill_id not in ids:
            ids.append(skill_id)
            r.set(REDIS_SKILLS_INDEX, json.dumps(ids))
        logger.info("Registered skill %s in Redis", skill_id)
    except Exception as e:
        logger.warning("Failed to register skill %s: %s", skill_id, e)


def append_tool_to_available(tool: dict, redis_url: str | None = None) -> None:
    """
    Append one tool to tools:available. Builder calls this when it adds a new capability.
    Tool shape: { name, description, constraints }.
    """
    try:
        r = get_redis_client(redis_url)
        raw = r.get(REDIS_TOOLS_KEY)
        tools = json.loads(raw) if raw else []
        if not isinstance(tools, list):
            tools = []
        tools.append(tool)
        r.set(REDIS_TOOLS_KEY, json.dumps(tools))
        logger.info("Appended tool %s to %s", tool.get("name", "?"), REDIS_TOOLS_KEY)
    except Exception as e:
        logger.warning("Failed to append tool: %s", e)
