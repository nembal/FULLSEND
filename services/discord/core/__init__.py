"""Core modules for the Discord Communication Service."""

from .bus import RedisBus, CHANNEL_TO_AGENT, CHANNEL_FROM_AGENT, publish_to_agent, subscribe_from_agent
from .messages import (
    AgentMessage,
    AgentMessageType,
    HumanMessage,
    HumanMessageType,
    ActionRequest,
    ActionType,
    IdeaSubmission,
    MessagePriority,
)
from .router import MessageRouter

__all__ = [
    # Bus
    "RedisBus",
    "CHANNEL_TO_AGENT",
    "CHANNEL_FROM_AGENT",
    "publish_to_agent",
    "subscribe_from_agent",
    # Router
    "MessageRouter",
    # Messages
    "AgentMessage",
    "AgentMessageType",
    "HumanMessage",
    "HumanMessageType",
    "ActionRequest",
    "ActionType",
    "IdeaSubmission",
    "MessagePriority",
]
