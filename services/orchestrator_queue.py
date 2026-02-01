"""
RabbitMQ topic/queue for orchestrator tasks. Roundtable publishes individual tasks;
orchestrator agent (later) consumes and runs them.
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

DEFAULT_QUEUE_NAME = "fullsend.orchestrator.tasks"
DEFAULT_URL = "amqp://localhost:5672/"


class OrchestratorQueue:
    """
    RabbitMQ queue for next tasks to run. Producers (e.g. roundtable) publish
    individual tasks; the orchestrator agent consumes and runs them (later).
    """

    def __init__(
        self,
        url: str | None = None,
        queue_name: str | None = None,
    ):
        self._url = url or os.getenv("RABBITMQ_URL", DEFAULT_URL)
        self._queue_name = queue_name or os.getenv("ORCHESTRATOR_QUEUE_NAME", DEFAULT_QUEUE_NAME)
        self._connection = None
        self._channel = None

    def connect(self) -> None:
        """Connect to RabbitMQ and declare the queue (durable)."""
        try:
            params = pika.URLParameters(self._url)
            self._connection = pika.BlockingConnection(params)
            self._channel = self._connection.channel()
            self._channel.queue_declare(queue=self._queue_name, durable=True)
            logger.info("OrchestratorQueue connected to %s queue %s", self._url.split("@")[-1] if "@" in self._url else self._url, self._queue_name)
        except Exception as e:
            logger.warning("OrchestratorQueue connect failed: %s", e)
            self._connection = None
            self._channel = None
            raise

    def publish_task(self, task: str | dict[str, Any], order: int | None = None) -> None:
        """
        Publish one task to the orchestrator queue. Body is JSON.
        task: either a string (task description) or dict with at least "task" key.
        order: optional 1-based index for sequencing.
        """
        if self._channel is None:
            raise RuntimeError("OrchestratorQueue not connected; call connect() first")
        if isinstance(task, str):
            payload = {"task": task, "source": "roundtable", "created_at": datetime.now(tz=timezone.utc).isoformat()}
        else:
            payload = dict(task)
            payload.setdefault("source", "roundtable")
            payload.setdefault("created_at", datetime.now(tz=timezone.utc).isoformat())
        if order is not None:
            payload["order"] = order
        body = json.dumps(payload).encode("utf-8")
        self._channel.basic_publish(
            exchange="",
            routing_key=self._queue_name,
            body=body,
            properties=pika.BasicProperties(delivery_mode=2),  # persistent
        )
        logger.debug("Published task (order=%s) to %s", order, self._queue_name)

    def disconnect(self) -> None:
        """Close channel and connection."""
        try:
            if self._channel:
                self._channel.close()
            if self._connection:
                self._connection.close()
        except Exception as e:
            logger.debug("OrchestratorQueue disconnect: %s", e)
        finally:
            self._channel = None
            self._connection = None

    @property
    def is_connected(self) -> bool:
        return self._connection is not None and self._connection.is_open
