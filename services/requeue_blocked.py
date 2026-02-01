"""
Requeue task payloads that had blocked items back to the orchestrator queue
so they can be re-planned after new tools are added (self-improving demo).
"""

import json
import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def get_task_states_with_blocked() -> list[dict]:
    """Load all task:{uuid} from Redis that have non-empty blocked. Returns list of { task_id, context, topic, order, blocked }."""
    from services.orchestrator.tools_loader import get_redis_client, REDIS_TASK_PREFIX

    try:
        r = get_redis_client()
        keys = [k for k in r.keys(f"{REDIS_TASK_PREFIX}*") if not k.endswith(":blocked")]
        out = []
        for key in keys:
            raw = r.get(key)
            if not raw:
                continue
            data = json.loads(raw)
            blocked = data.get("blocked") or []
            if not blocked:
                continue
            task_id = key.replace(REDIS_TASK_PREFIX, "")
            out.append({
                "task_id": task_id,
                "context": data.get("context", ""),
                "topic": data.get("topic", ""),
                "order": data.get("order"),
                "blocked": blocked,
            })
        return out
    except Exception as e:
        logger.warning("Failed to load task states from Redis: %s", e)
        return []


def get_all_task_states() -> list[dict]:
    """Load all task:{uuid} from Redis (not :blocked keys). Returns list of { task_id, context, next_steps, blocked, topic, order }."""
    from services.orchestrator.tools_loader import get_redis_client, REDIS_TASK_PREFIX

    try:
        r = get_redis_client()
        keys = [k for k in r.keys(f"{REDIS_TASK_PREFIX}*") if not k.endswith(":blocked")]
        out = []
        for key in keys:
            raw = r.get(key)
            if not raw:
                continue
            data = json.loads(raw)
            task_id = key.replace(REDIS_TASK_PREFIX, "")
            out.append({
                "task_id": task_id,
                "context": data.get("context", ""),
                "next_steps": data.get("next_steps") or [],
                "blocked": data.get("blocked") or [],
                "topic": data.get("topic", ""),
                "order": data.get("order"),
            })
        return out
    except Exception as e:
        logger.warning("Failed to load all task states from Redis: %s", e)
        return []


def requeue_blocked_tasks() -> int:
    """
    Publish each task payload that had blocked items back to the orchestrator queue,
    then delete those task states from Redis so we don't accumulate old states.
    Returns number of tasks requeued.
    """
    from services.orchestrator.tools_loader import delete_task_state
    from services.orchestrator_queue import OrchestratorQueue

    tasks = get_task_states_with_blocked()
    if not tasks:
        logger.info("Requeue: no tasks with blocked items to requeue")
        return 0
    try:
        queue = OrchestratorQueue()
        queue.connect()
        for i, t in enumerate(tasks, 1):
            queue.publish_task(
                {"task": t["context"], "topic": t["topic"], "source": "requeue_demo"},
                order=t.get("order") or i,
            )
            delete_task_state(t["task_id"])
        queue.disconnect()
        logger.info("Requeued %d task(s) to orchestrator queue and deleted from Redis", len(tasks))
        return len(tasks)
    except Exception as e:
        logger.warning("Requeue failed: %s", e)
        return 0
