"""
Orchestrator daemon: consume tasks from queue, assign task_id via hash_service,
generate implementation steps via orchestrator LLM, publish each step to worker steps queue.
Uses Weave (W&B) for monitoring; same project as roundtable.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone

import pika
import weave
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage

from .llm import get_orchestrator_llm

load_dotenv()

logger = logging.getLogger(__name__)

weave.init("viswanathkothe-syracuse-university/weavehacks")

DEFAULT_RABBITMQ_URL = "amqp://localhost:5672/"
DEFAULT_ORCHESTRATOR_QUEUE = "fullsend.orchestrator.tasks"
DEFAULT_STEPS_QUEUE = "fullsend.worker.steps"

STEPS_SYSTEM_TEMPLATE = """You are an implementation planner. Given a single GTM task from a roundtable and the available downstream agents/tools, output two lists in JSON:

1) next_tasks: 3–8 concrete, ordered implementation steps that the available agents CAN execute (use only the tools listed below).
2) blocked_tasks: any steps that CANNOT be carried out with current tools; for each give "task" (short description) and "reason" (why it cannot be done).

Available tools (only propose next_tasks that these can carry out):
{tools_context}

Output only a JSON object with this exact shape (no markdown, no code fence):
{{"next_tasks": ["step 1", "step 2", ...], "blocked_tasks": [{{"task": "short desc", "reason": "why blocked"}}, ...]}}
- If all steps are doable, blocked_tasks can be [].
- If nothing is doable with current tools, next_tasks can be [] and blocked_tasks must explain why."""


def _parse_twofold_from_llm(response: str) -> tuple[list[str], list[dict]]:
    """Extract next_tasks and blocked_tasks from LLM JSON. Returns (next_tasks, blocked_tasks)."""
    text = response.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    try:
        data = json.loads(text)
        next_tasks = data.get("next_tasks") or []
        blocked_tasks = data.get("blocked_tasks") or []
        next_steps = [s.strip() for s in next_tasks if isinstance(s, str) and s.strip()]
        blocked = [
            {"task": b.get("task", ""), "reason": b.get("reason", "")}
            for b in blocked_tasks
            if isinstance(b, dict)
        ]
        return next_steps, blocked
    except json.JSONDecodeError:
        return [response.strip()] if response.strip() else [], []


@weave.op
def process_one_task(task_payload: dict, llm, tools_context: str) -> dict:
    """
    Generate task_id and two-fold implementation plan for one orchestrator task. Traced in Weave.
    Returns {"task_id": str, "next_steps": list[str], "blocked": list[dict]}.
    """
    from services.hash_service import generate_task_id

    task_text = task_payload.get("task", "").strip()
    topic = task_payload.get("topic", "")
    task_id = generate_task_id()
    system = STEPS_SYSTEM_TEMPLATE.format(tools_context=tools_context)
    messages = [
        SystemMessage(content=system),
        HumanMessage(content=f"GTM task:\n{task_text}\n\nTopic: {topic}\n\nOutput JSON with next_tasks (steps the executor Claude Code + Browserbase can run) and blocked_tasks (steps it cannot run yet)."),
    ]
    response = llm.invoke(messages)
    response_text = response.content if hasattr(response, "content") else str(response)
    next_steps, blocked = _parse_twofold_from_llm(response_text)
    return {"task_id": task_id, "next_steps": next_steps, "blocked": blocked}


def run_orchestrator_daemon(
    rabbitmq_url: str | None = None,
    orchestrator_queue_name: str | None = None,
    steps_queue_name: str | None = None,
    max_messages: int | None = None,
    time_limit_seconds: float | None = None,
) -> None:
    """
    Consume from orchestrator queue, plan steps, publish to steps queue, write task state to Redis.
    If max_messages is set, process up to that many messages then stop (for batch/demo).
    If time_limit_seconds is set, process for at most that many seconds then stop (avoids hanging if queue is empty).
    Otherwise run forever.
    """
    url = rabbitmq_url or os.getenv("RABBITMQ_URL", DEFAULT_RABBITMQ_URL)
    in_queue = orchestrator_queue_name or os.getenv("ORCHESTRATOR_QUEUE_NAME", DEFAULT_ORCHESTRATOR_QUEUE)
    out_queue = steps_queue_name or os.getenv("STEPS_QUEUE_NAME", DEFAULT_STEPS_QUEUE)

    if not os.getenv("RABBITMQ_URL"):
        logger.warning("RABBITMQ_URL not set; using default %s", DEFAULT_RABBITMQ_URL)

    from .tools_loader import format_tools_for_prompt, get_available_tools, write_blocked_only, write_task_state

    tools = get_available_tools()
    tools_context = format_tools_for_prompt(tools)
    logger.info("Loaded %d available tools for orchestrator (from Redis or file)", len(tools))

    llm = get_orchestrator_llm()
    params = pika.URLParameters(url)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
    channel.queue_declare(queue=in_queue, durable=True)
    channel.queue_declare(queue=out_queue, durable=True)

    def publish_step(task_id: str, task_payload: dict, step_index: int, step_text: str) -> None:
        payload = {
            "task_id": task_id,
            "task": task_payload.get("task", ""),
            "topic": task_payload.get("topic", ""),
            "order": task_payload.get("order"),
            "step_index": step_index,
            "step": step_text,
            "source": "orchestrator",
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        body = json.dumps(payload).encode("utf-8")
        channel.basic_publish(
            exchange="",
            routing_key=out_queue,
            body=body,
            properties=pika.BasicProperties(delivery_mode=2),
        )

    def on_message(ch, method, properties, body):
        try:
            task_payload = json.loads(body.decode("utf-8"))
        except Exception as e:
            logger.exception("Invalid task JSON: %s", e)
            ch.basic_nack(method.delivery_tag, requeue=False)
            return

        logger.info("Processing order=%s topic=%s", task_payload.get("order"), (task_payload.get("topic") or "")[:50])

        try:
            result = process_one_task(task_payload, llm, tools_context)
            task_id = result["task_id"]
            next_steps = result["next_steps"]
            blocked = result["blocked"]
            for i, step in enumerate(next_steps, start=1):
                publish_step(task_id, task_payload, i, step)
            if blocked:
                write_blocked_only(task_id, blocked)
                logger.info("Wrote %d blocked items for task_id=%s to Redis", len(blocked), task_id)
            context = task_payload.get("task", "") or ""
            topic_val = task_payload.get("topic", "")
            order_val = task_payload.get("order")
            write_task_state(
                task_id, context=context, next_steps=next_steps, blocked=blocked,
                topic=topic_val, order=order_val,
            )
            logger.info("Published %d steps for task_id=%s to %s; task state written to Redis", len(next_steps), task_id, out_queue)
        except Exception as e:
            logger.exception("LLM or publish failed: %s", e)
            ch.basic_nack(method.delivery_tag, requeue=True)
            return

        ch.basic_ack(method.delivery_tag)
        processed[0] += 1
        if max_messages is not None and processed[0] >= max_messages:
            ch.stop_consuming()
        elif max_messages is not None:
            # Stop when queue is empty so we don't hang if another consumer took some messages
            try:
                decl = ch.queue_declare(queue=in_queue, passive=True)
                if decl.method.message_count == 0:
                    ch.stop_consuming()
            except Exception:
                pass

    processed: list[int] = [0]
    channel.basic_qos(prefetch_count=1)
    consumer_tag = channel.basic_consume(queue=in_queue, on_message_callback=on_message)
    desc = []
    if max_messages is not None:
        desc.append(f"max {max_messages}")
    if time_limit_seconds is not None:
        desc.append(f"time limit {time_limit_seconds}s")
    logger.info(
        "Orchestrator %s. Consuming from %s, publishing steps to %s.",
        "batch (" + ", ".join(desc) + ")" if desc else "daemon started",
        in_queue,
        out_queue,
    )
    if time_limit_seconds is not None:
        connection.process_data_events(time_limit=time_limit_seconds)
        try:
            channel.basic_cancel(consumer_tag)
        except Exception:
            pass
        logger.info("Orchestrator time limit reached; processed %d message(s)", processed[0])
    else:
        channel.start_consuming()
