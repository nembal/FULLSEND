"""
Analyzer agent: load all blocked (unrunnable) tasks from Redis, run a roundtable
to propose what tools to build, publish clear "Do this first / Do this next"
instructions to the builder queue.
"""

import json
import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def load_all_blocked_from_redis() -> list[dict]:
    """
    Load all blocked tasks from Redis (task:*:blocked and task:* .blocked).
    Returns list of {"task": str, "reason": str} (deduplicated by task+reason).
    """
    try:
        import redis
    except ImportError:
        logger.warning("redis not installed; returning empty blocked list")
        return []

    try:
        r = redis.from_url(REDIS_URL, decode_responses=True)
        r.ping()
    except Exception as e:
        logger.warning("Redis connection failed: %s", e)
        return []

    seen = set()
    out = []

    # task:*:blocked
    for key in r.keys("task:*:blocked"):
        try:
            raw = r.get(key)
            if not raw:
                continue
            blocked = json.loads(raw)
            for b in blocked if isinstance(blocked, list) else [blocked]:
                if not isinstance(b, dict):
                    continue
                task_desc = b.get("task", "").strip()
                reason = b.get("reason", "").strip()
                key_ = (task_desc, reason)
                if key_ not in seen:
                    seen.add(key_)
                    out.append({"task": task_desc, "reason": reason})
        except Exception as e:
            logger.debug("Error reading %s: %s", key, e)

    # task:* (full state) .blocked
    for key in r.keys("task:*"):
        if key.endswith(":blocked"):
            continue
        try:
            raw = r.get(key)
            if not raw:
                continue
            data = json.loads(raw)
            for b in data.get("blocked") or []:
                if not isinstance(b, dict):
                    continue
                task_desc = b.get("task", "").strip()
                reason = b.get("reason", "").strip()
                key_ = (task_desc, reason)
                if key_ not in seen:
                    seen.add(key_)
                    out.append({"task": task_desc, "reason": reason})
        except Exception as e:
            logger.debug("Error reading %s: %s", key, e)

    return out


def format_blocked_for_seed_context(blocked: list[dict]) -> str:
    """Format blocked list as a string for roundtable seed_context."""
    if not blocked:
        return "There are no blocked steps in Redis yet. Consider running the orchestrator first so some GTM tasks produce blocked steps (steps the executor Claude Code + Browserbase could not run with current capabilities)."
    lines = [
        "Blocked steps (the executor Claude Code + Browserbase could not run with current capabilities). "
        "The builder (Ralph loop on Claude Code) will get instructions to add missing skills:"
    ]
    for i, b in enumerate(blocked, 1):
        task = b.get("task", "")
        reason = b.get("reason", "")
        lines.append(f"  {i}. {task}")
        if reason:
            lines.append(f"     Reason: {reason}")
    return "\n".join(lines)


def run_analyzer() -> dict:
    """
    Run the analyzer: load blocked tasks from Redis, run roundtable with that context,
    publish summary to builder queue (Do this first / Do this next). Returns roundtable result.
    """
    from services.roundtable.runner import run_roundtable

    blocked = load_all_blocked_from_redis()
    logger.info("Loaded %d blocked task(s) from Redis", len(blocked))

    seed_context = format_blocked_for_seed_context(blocked)
    topic = (
        "What tools or capabilities should we build so that these blocked GTM tasks can run? "
        "Propose 3–5 concrete builder tasks in the format: Do this first: [one clear instruction] "
        "Do this next: [...] Do this third: [...] (same style as a Do-this list)."
    )

    result = run_roundtable(
        topic=topic,
        seed_context=seed_context,
        publish_to="builder",
        max_rounds=2,
        builder_context={"blocked_context": blocked},
    )
    return result
