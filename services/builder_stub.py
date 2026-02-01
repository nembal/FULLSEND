"""
Demo builder stub: consumes from builder queue and adds minimal tools/skills to Redis
so the next orchestrator cycle sees new tools (self-improving demo). No real code generation.
"""

import json
import logging
import os
import re

import pika
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_URL = "amqp://localhost:5672/"
DEFAULT_BUILDER_QUEUE = "fullsend.builder.tasks"


def _task_to_slug(task_text: str, order: int) -> str:
    """Derive a short slug from builder task text (e.g. 'Build a HubSpot sync agent' -> hubspot-sync)."""
    text = (task_text or "").strip()[:80]
    # Take first few words, lowercase, keep alphanumeric and spaces, then replace spaces with hyphen
    words = re.sub(r"[^a-zA-Z0-9\s]", "", text).lower().split()[:5]
    base = "-".join(w for w in words if w)
    return base or f"tool-{order}"


def run_builder_stub(max_messages: int | None = None) -> tuple[int, list[str]]:
    """
    Consume from builder queue; for each message add a minimal tool to tools:available
    and a stub skill to Redis. Returns (number processed, list of tool slugs added).
    """
    from services.orchestrator.tools_loader import append_tool_to_available, register_skill

    url = os.getenv("RABBITMQ_URL", DEFAULT_URL)
    queue_name = os.getenv("BUILDER_QUEUE_NAME", DEFAULT_BUILDER_QUEUE)

    try:
        params = pika.URLParameters(url)
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        channel.queue_declare(queue=queue_name, durable=True)
    except Exception as e:
        logger.warning("Builder stub: RabbitMQ connect failed: %s", e)
        return 0, []

    processed = 0
    added_slugs: list[str] = []
    while True:
        if max_messages is not None and processed >= max_messages:
            break
        method, _, body = channel.basic_get(queue=queue_name, auto_ack=False)
        if method is None:
            break
        try:
            payload = json.loads(body.decode("utf-8"))
            task_text = payload.get("task", "").strip()
            order = payload.get("order", processed + 1)
            blocked_context = payload.get("blocked_context") or []

            slug = _task_to_slug(task_text, order)
            name = slug.replace("-", " ").title()
            tool = {
                "name": slug,
                "description": f"{name} (skill added by builder; Ralph loop on Claude Code).",
                "constraints": "Added by builder queue; replace with real implementation when Ralph loop implements it.",
            }
            append_tool_to_available(tool)
            register_skill(
                skill_id=slug,
                name=name,
                description=tool["description"],
                content="# Skill added by builder (Ralph loop). Replace with real SKILL.md or implementation.",
                addresses_blocked=blocked_context[:3],
            )
            added_slugs.append(slug)
            logger.info("Builder stub: added tool and skill %s", slug)
        except Exception as e:
            logger.exception("Builder stub: failed to process message: %s", e)
            channel.basic_nack(method.delivery_tag, requeue=True)
            connection.close()
            return processed, added_slugs
        channel.basic_ack(method.delivery_tag)
        processed += 1

    connection.close()
    logger.info("Builder stub: processed %d message(s), added %s", processed, added_slugs)
    return processed, added_slugs
