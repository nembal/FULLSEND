"""Escalation payload builder for sending messages to Orchestrator."""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from .classifier import Classification

logger = logging.getLogger(__name__)


class EscalationContext(BaseModel):
    """Context information for an escalation."""

    channel: str = Field(description="Discord channel name where message originated")
    user: str = Field(description="Username who sent the message")
    summary: str = Field(description="Brief summary of why this is being escalated")


class EscalationPayload(BaseModel):
    """Payload shape for escalations to fullsend:to_orchestrator."""

    type: str = Field(default="escalation", description="Message type identifier")
    source: str = Field(default="watcher", description="Service that generated the escalation")
    priority: str = Field(description="Priority level: low|medium|high|urgent")
    reason: str = Field(description="Explanation of why this message is being escalated")
    original_message: dict[str, Any] = Field(description="The original Discord message")
    context: EscalationContext = Field(description="Contextual information for the Orchestrator")
    timestamp: str = Field(description="ISO8601 timestamp of escalation")


def build_escalation(
    msg: dict[str, Any],
    classification: Classification,
    summary: Optional[str] = None,
) -> EscalationPayload:
    """Build an escalation payload from a message and its classification.

    Args:
        msg: The original Discord message dict
        classification: The classification result from the classifier
        summary: Optional custom summary; defaults to classification.reason

    Returns:
        EscalationPayload ready to be serialized and published
    """
    return EscalationPayload(
        type="escalation",
        source="watcher",
        priority=classification.priority,
        reason=classification.reason,
        original_message=msg,
        context=EscalationContext(
            channel=msg.get("channel_name", "unknown"),
            user=msg.get("username", "unknown"),
            summary=summary or classification.reason,
        ),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def build_error_escalation(
    msg: dict[str, Any],
    error: Exception,
    error_type: str = "classification_error",
) -> EscalationPayload:
    """Build an escalation payload for error conditions.

    Used when classification fails and we need to escalate for human review.

    Args:
        msg: The original Discord message dict
        error: The exception that occurred
        error_type: Category of error for tracking

    Returns:
        EscalationPayload with error context
    """
    reason = f"{error_type}: {str(error)}"
    return EscalationPayload(
        type="escalation",
        source="watcher",
        priority="medium",  # Errors get medium priority - needs attention but not urgent
        reason=reason,
        original_message=msg,
        context=EscalationContext(
            channel=msg.get("channel_name", "unknown"),
            user=msg.get("username", "unknown"),
            summary=f"Watcher error: {error_type} - escalating for human review",
        ),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


async def publish_escalation(
    payload: EscalationPayload,
    redis_client: Any,
    channel: str,
) -> None:
    """Publish an escalation payload to Redis.

    Args:
        payload: The escalation payload to publish
        redis_client: Async Redis client
        channel: Redis channel to publish to (e.g., fullsend:to_orchestrator)
    """
    payload_json = payload.model_dump_json()
    await redis_client.publish(channel, payload_json)
    logger.info(
        f"Published escalation to {channel}: priority={payload.priority}, "
        f"reason={payload.reason[:50]}..."
    )


# Allow running escalator directly for testing
if __name__ == "__main__":
    import sys

    if sys.stdin.isatty():
        print("Usage: echo '{\"content\": \"test\", \"username\": \"user\", \"channel_name\": \"test-channel\"}' | python -m services.watcher.escalator")
        sys.exit(1)

    input_data = json.loads(sys.stdin.read())

    # Create a mock classification for testing
    mock_classification = Classification(
        action="escalate",
        reason="Test escalation",
        priority="medium",
    )

    payload = build_escalation(input_data, mock_classification)
    print(payload.model_dump_json(indent=2))
