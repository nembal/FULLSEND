"""
Redis tools for the GTM orchestrator agent.
Uses REDIS_URL from env (e.g. redis://localhost:6379).
Keys: gtm:learnings, gtm:hypotheses, gtm:tools, gtm:experiments (lists in Redis).
"""
import os
import json
from typing import Optional

from langchain_core.tools import tool

# Lazy Redis client so we don't require redis at import if not used
_redis_client = None

def _get_redis():
    global _redis_client
    if _redis_client is None:
        import redis
        url = os.getenv("REDIS_URL", "redis://localhost:6379")
        _redis_client = redis.from_url(url, decode_responses=True)
    return _redis_client

def _key(name: str) -> str:
    return f"gtm:{name}"

@tool
def redis_get_learnings() -> str:
    """Get all GTM learnings stored in Redis (sector/product learnings, outreach patterns, what worked)."""
    try:
        r = _get_redis()
        items = r.lrange(_key("learnings"), 0, -1)
        if not items:
            return "No learnings stored yet."
        return "\n".join(items)
    except Exception as e:
        return f"Redis error: {e}"

@tool
def redis_add_learning(learning: str) -> str:
    """Add a GTM learning to Redis (e.g. 'Event attendee mining: high signal' or 'CFOs respond to compliance angles')."""
    try:
        r = _get_redis()
        r.rpush(_key("learnings"), learning)
        return f"Added learning: {learning}"
    except Exception as e:
        return f"Redis error: {e}"

@tool
def redis_get_hypotheses() -> str:
    """Get all GTM hypotheses stored in Redis (tested or active)."""
    try:
        r = _get_redis()
        items = r.lrange(_key("hypotheses"), 0, -1)
        if not items:
            return "No hypotheses stored yet."
        return "\n".join(items)
    except Exception as e:
        return f"Redis error: {e}"

@tool
def redis_add_hypothesis(hypothesis: str) -> str:
    """Log a GTM hypothesis to Redis (e.g. 'Target AI DevTools Summit attendees')."""
    try:
        r = _get_redis()
        r.rpush(_key("hypotheses"), hypothesis)
        return f"Added hypothesis: {hypothesis}"
    except Exception as e:
        return f"Redis error: {e}"

@tool
def redis_list_tools() -> str:
    """List tool names/descriptions stored in Redis (agent-built tools)."""
    try:
        r = _get_redis()
        items = r.lrange(_key("tools"), 0, -1)
        if not items:
            return "No tools registered yet."
        return "\n".join(items)
    except Exception as e:
        return f"Redis error: {e}"

@tool
def redis_register_tool(description: str) -> str:
    """Register a tool in Redis (e.g. 'LinkedIn event scraper')."""
    try:
        r = _get_redis()
        r.rpush(_key("tools"), description)
        return f"Registered tool: {description}"
    except Exception as e:
        return f"Redis error: {e}"

def get_redis_tools():
    """Return list of LangChain tools for Redis context."""
    return [
        redis_get_learnings,
        redis_add_learning,
        redis_get_hypotheses,
        redis_add_hypothesis,
        redis_list_tools,
        redis_register_tool,
    ]
