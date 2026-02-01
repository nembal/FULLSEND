"""
Executor worker: consume from fullsend.worker.steps, load task + skills from Redis,
run Claude Code (Browserbase) for each step, update task state in Redis,
publish what worked / what didn't to RabbitMQ result queues.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import pika
from dotenv import load_dotenv

from services.orchestrator.tools_loader import (
    get_skill,
    get_task_state,
    list_skills,
    update_task_after_step,
)

from .runner import run as run_executor

_project_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(_project_root / ".env")

logger = logging.getLogger(__name__)

DEFAULT_RABBITMQ_URL = "amqp://localhost:5672/"
DEFAULT_STEPS_QUEUE = "fullsend.worker.steps"
DEFAULT_RESULTS_WORKED_QUEUE = "fullsend.worker.results.worked"
DEFAULT_RESULTS_FAILED_QUEUE = "fullsend.worker.results.failed"
RESULT_LOG_MAX_LEN = 400
ERROR_PREVIEW_MAX_LEN = 500


def _result_worked(result: str) -> bool:
    """True if result looks like success (no executor error prefix or obvious failure)."""
    if not (result or "").strip():
        return False
    r = result.strip()
    if r.startswith("Executor:"):
        return False
    lower = r.lower()
    if "invalid api key" in lower or "please run /login" in lower:
        return False
    if "error:" in lower or "failed:" in lower or ("not found" in lower and "claude" in lower):
        return False
    return True


def _log_step_outcome(task_id: str, step_index: int, step_text: str, result: str) -> None:
    """Log what worked / what didn't for this step."""
    worked = _result_worked(result)
    status = "WORKED" if worked else "DID NOT WORK"
    step_preview = (step_text or "")[:80] + ("..." if len(step_text or "") > 80 else "")
    result_preview = (result or "").strip()
    if len(result_preview) > RESULT_LOG_MAX_LEN:
        result_preview = result_preview[:RESULT_LOG_MAX_LEN] + "..."
    logger.info("[%s] task_id=%s step_index=%s | %s", status, task_id, step_index, step_preview)
    logger.info("  result: %s", result_preview or "(empty)")
    if not worked:
        logger.warning("  step DID NOT WORK — check result above for task_id=%s step_index=%s", task_id, step_index)


def _publish_step_result(
    channel,
    payload: dict,
    result: str,
    worked: bool,
    results_worked_queue: str,
    results_failed_queue: str,
) -> None:
    """Publish step outcome to fullsend.worker.results.worked or .failed."""
    msg = {
        "task_id": payload.get("task_id", ""),
        "task": payload.get("task", ""),
        "topic": payload.get("topic", ""),
        "order": payload.get("order"),
        "step_index": payload.get("step_index", 0),
        "step": payload.get("step", ""),
        "result": (result or "").strip(),
        "source": "executor",
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    if worked:
        routing_key = results_worked_queue
    else:
        msg["error_preview"] = (result or "").strip()[:ERROR_PREVIEW_MAX_LEN]
        routing_key = results_failed_queue
    body = json.dumps(msg).encode("utf-8")
    channel.basic_publish(
        exchange="",
        routing_key=routing_key,
        body=body,
        properties=pika.BasicProperties(delivery_mode=2),
    )


def build_skills_context(redis_url: str | None = None) -> str:
    """Load all skills from Redis and format as context for the executor prompt."""
    ids = list_skills(redis_url)
    if not ids:
        return ""
    parts = ["Available skills (from Redis; use as needed):"]
    for sid in ids:
        skill = get_skill(sid, redis_url)
        if not skill:
            continue
        name = skill.get("name") or sid
        desc = (skill.get("description") or "").strip()
        content = (skill.get("content") or "").strip()
        parts.append(f"\n## {sid}: {name}")
        if desc:
            parts.append(desc)
        if content:
            parts.append(content)
    return "\n".join(parts).strip()


def run_executor_daemon(
    rabbitmq_url: str | None = None,
    steps_queue_name: str | None = None,
    redis_url: str | None = None,
    max_messages: int | None = None,
    time_limit_seconds: float | None = None,
) -> None:
    """
    Consume from worker steps queue; for each step load task + skills from Redis,
    run executor (Claude Code + Browserbase), update task state in Redis.
    """
    url = rabbitmq_url or os.getenv("RABBITMQ_URL", DEFAULT_RABBITMQ_URL)
    queue_name = steps_queue_name or os.getenv("STEPS_QUEUE_NAME", DEFAULT_STEPS_QUEUE)
    worked_queue = os.getenv("WORKER_RESULTS_WORKED_QUEUE", DEFAULT_RESULTS_WORKED_QUEUE)
    failed_queue = os.getenv("WORKER_RESULTS_FAILED_QUEUE", DEFAULT_RESULTS_FAILED_QUEUE)

    params = pika.URLParameters(url)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
    channel.queue_declare(queue=queue_name, durable=True)
    channel.queue_declare(queue=worked_queue, durable=True)
    channel.queue_declare(queue=failed_queue, durable=True)

    processed: list[int] = [0]

    def on_message(ch, method, properties, body):
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception as e:
            logger.exception("Invalid step JSON: %s", e)
            ch.basic_nack(method.delivery_tag, requeue=False)
            return

        task_id = payload.get("task_id", "")
        step_index = payload.get("step_index", 0)
        step_text = (payload.get("step") or "").strip()
        gtm_task = (payload.get("task") or "").strip()
        topic = (payload.get("topic") or "").strip()

        if not step_text:
            logger.warning("Empty step for task_id=%s; ack and skip", task_id)
            ch.basic_ack(method.delivery_tag)
            processed[0] += 1
            return

        try:
            # Load task state from Redis for full context
            state = get_task_state(task_id, redis_url)
            context_parts = []
            if gtm_task:
                context_parts.append(f"GTM task: {gtm_task}")
            if topic:
                context_parts.append(f"Topic: {topic}")
            if state and state.get("previous_steps"):
                context_parts.append("Steps already done:")
                for p in state["previous_steps"]:
                    if isinstance(p, dict):
                        context_parts.append(f"  - {p.get('step', p)}")
                    else:
                        context_parts.append(f"  - {p}")

            # Load all skills from Redis for context
            skills_ctx = build_skills_context(redis_url)
            if skills_ctx:
                context_parts.append("\n" + skills_ctx)

            context = "\n".join(context_parts).strip()

            # Run executor (Claude Code with Browserbase)
            result = run_executor(
                task=step_text,
                context=context or None,
                steps=None,
            )

            # Log what worked / what didn't
            worked = _result_worked(result)
            _log_step_outcome(task_id, step_index, step_text, result)

            # Publish to RabbitMQ result queue (worked vs failed)
            _publish_step_result(
                channel,
                payload,
                result,
                worked,
                results_worked_queue=worked_queue,
                results_failed_queue=failed_queue,
            )

            # Update Redis: append to previous_steps, remove from next_steps
            update_task_after_step(
                task_id,
                step_index=step_index,
                step_text=step_text,
                result=result,
                redis_url=redis_url,
            )
        except Exception as e:
            logger.exception("Executor failed for task_id=%s step_index=%s: %s", task_id, step_index, e)
            ch.basic_nack(method.delivery_tag, requeue=True)
            return

        ch.basic_ack(method.delivery_tag)
        processed[0] += 1
        if max_messages is not None and processed[0] >= max_messages:
            ch.stop_consuming()
        elif max_messages is not None:
            try:
                decl = channel.queue_declare(queue=queue_name, passive=True)
                if decl.method.message_count == 0:
                    ch.stop_consuming()
            except Exception:
                pass

    channel.basic_qos(prefetch_count=1)
    consumer_tag = channel.basic_consume(queue=queue_name, on_message_callback=on_message)
    desc = []
    if max_messages is not None:
        desc.append(f"max {max_messages}")
    if time_limit_seconds is not None:
        desc.append(f"time limit {time_limit_seconds}s")
    logger.info(
        "Executor daemon %s. Consuming from %s (Redis skills + task context).",
        "batch (" + ", ".join(desc) + ")" if desc else "started",
        queue_name,
    )
    if time_limit_seconds is not None:
        connection.process_data_events(time_limit=time_limit_seconds)
        try:
            channel.basic_cancel(consumer_tag)
        except Exception:
            pass
        logger.info("Executor time limit reached; processed %d message(s)", processed[0])
    else:
        channel.start_consuming()
