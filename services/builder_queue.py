"""
RabbitMQ queue for builder tasks. Analyzer agent publishes clear "Do this first / Do this next"
instructions on what tools to build; builders consume and implement.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import pika
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_BUILDER_QUEUE_NAME = "fullsend.builder.tasks"
DEFAULT_URL = "amqp://localhost:5672/"


class BuilderQueue:
    """
    RabbitMQ queue for builder tasks. Producers (e.g. analyzer) publish
    instructions on what tools to build; builder agents consume (later).
    """

    def __init__(
        self,
        url: str | None = None,
        queue_name: str | None = None,
    ):
        self._url = url or os.getenv("RABBITMQ_URL", DEFAULT_URL)
        self._queue_name = queue_name or os.getenv("BUILDER_QUEUE_NAME", DEFAULT_BUILDER_QUEUE_NAME)
        self._connection = None
        self._channel = None

    def connect(self) -> None:
        """Connect to RabbitMQ and declare the queue (durable)."""
        try:
            params = pika.URLParameters(self._url)
            self._connection = pika.BlockingConnection(params)
            self._channel = self._connection.channel()
            self._channel.queue_declare(queue=self._queue_name, durable=True)
            logger.info("BuilderQueue connected to %s queue %s", self._url.split("@")[-1] if "@" in self._url else self._url, self._queue_name)
        except Exception as e:
            logger.warning("BuilderQueue connect failed: %s", e)
            self._connection = None
            self._channel = None
            raise

    def publish_task(
        self,
        task: str | dict[str, Any],
        order: int | None = None,
        topic: str = "",
        blocked_context: list[dict] | None = None,
    ) -> None:
        """Publish one builder task. Body is JSON with source=analyzer, format=builder_instruction, optional blocked_context."""
        if self._channel is None:
            raise RuntimeError("BuilderQueue not connected; call connect() first")
        if isinstance(task, str):
            payload = {"task": task, "source": "analyzer", "created_at": datetime.now(tz=timezone.utc).isoformat()}
        else:
            payload = dict(task)
            payload.setdefault("source", "analyzer")
            payload.setdefault("created_at", datetime.now(tz=timezone.utc).isoformat())
        if topic:
            payload.setdefault("topic", topic)
        if order is not None:
            payload["order"] = order
        payload["format"] = "builder_instruction"
        if blocked_context is not None:
            payload["blocked_context"] = blocked_context
        body = json.dumps(payload).encode("utf-8")
        self._channel.basic_publish(
            exchange="",
            routing_key=self._queue_name,
            body=body,
            properties=pika.BasicProperties(delivery_mode=2),
        )
        logger.debug("Published builder task (order=%s) to %s", order, self._queue_name)

    def disconnect(self) -> None:
        try:
            if self._channel:
                self._channel.close()
            if self._connection:
                self._connection.close()
        except Exception as e:
            logger.debug("BuilderQueue disconnect: %s", e)
        finally:
            self._channel = None
            self._connection = None

    @property
    def is_connected(self) -> bool:
        return self._connection is not None and self._connection.is_open
