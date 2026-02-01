"""Message models for the Discord communication service.

These models define the structure of messages passed between the Discord bot,
web adapter, and the orchestrator via Redis pub/sub.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class MessagePriority(str, Enum):
    """Priority levels for agent messages."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class AgentMessageType(str, Enum):
    """Types of messages from the orchestrator/agent."""

    STATUS_UPDATE = "status_update"
    ACTION_REQUEST = "action_request"
    IDEA_ACK = "idea_ack"
    LEARNING_SHARE = "learning_share"
    WIN_ALERT = "win_alert"
    IDEA_REQUEST = "idea_request"
    ERROR = "error"


class HumanMessageType(str, Enum):
    """Types of messages from humans to the orchestrator."""

    IDEA_SUBMIT = "idea_submit"
    ACTION_COMPLETE = "action_complete"
    COMMAND = "command"
    CONFIG_UPDATE = "config_update"


class ActionType(str, Enum):
    """Types of actions that can be requested."""

    MANUAL_TASK = "manual_task"
    APPROVAL = "approval"
    REVIEW = "review"
    DECISION = "decision"
    FEEDBACK = "feedback"


class AgentMessage(BaseModel):
    """Message from the agent/orchestrator to Discord.

    Used for status updates, action requests, and other outbound messages.
    """

    type: AgentMessageType = Field(..., description="Type of the message")
    payload: dict[str, Any] = Field(default_factory=dict, description="Message payload data")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="When the message was created")
    priority: MessagePriority = Field(default=MessagePriority.NORMAL, description="Message priority level")


class ActionRequest(BaseModel):
    """Request for human action from the orchestrator.

    Posted to the status channel with reaction buttons for completion.
    """

    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique identifier for the action")
    description: str = Field(..., description="Human-readable description of what needs to be done")
    action_type: ActionType = Field(..., description="Type of action requested")
    details: dict[str, Any] = Field(default_factory=dict, description="Additional details about the action")
    assignee: str | None = Field(default=None, description="Optional user ID of the assignee")
    deadline: datetime | None = Field(default=None, description="Optional deadline for the action")


class HumanMessage(BaseModel):
    """Message from a human to the orchestrator.

    Used for commands, idea submissions, and action completions.
    """

    type: HumanMessageType = Field(..., description="Type of the message")
    payload: dict[str, Any] = Field(default_factory=dict, description="Message payload data")
    source: str = Field(..., description="Source of the message (discord/web)")
    user_id: str = Field(..., description="Identifier of the user who sent the message")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="When the message was created")


class IdeaSubmission(BaseModel):
    """Idea submitted by a human for processing.

    Can come from slash commands or ambient channel listening.
    """

    content: str = Field(..., description="The idea content text")
    source_channel: str = Field(..., description="Channel where the idea was submitted")
    submitted_by: str = Field(..., description="User ID or name who submitted the idea")
    context: dict[str, Any] = Field(default_factory=dict, description="Additional context about the submission")
