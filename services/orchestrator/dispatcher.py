"""Dispatcher for Orchestrator - sends tasks to FULLSEND, Builder, Discord, Roundtable."""

import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

import redis.asyncio as redis

from .config import Settings
from .context import append_learning, update_worklist

logger = logging.getLogger(__name__)


@dataclass
class Decision:
    """Parsed decision from the Orchestrator agent."""

    action: Literal[
        "dispatch_to_fullsend",
        "dispatch_to_builder",
        "respond_to_discord",
        "update_worklist",
        "record_learning",
        "kill_experiment",
        "initiate_roundtable",
        "no_action",
    ]
    reasoning: str
    payload: dict[str, Any]
    priority: Literal["low", "medium", "high", "urgent"]
    experiment_id: str | None = None
    context_for_fullsend: str | None = None


class Dispatcher:
    """Handles dispatching decisions to appropriate services."""

    def __init__(self, redis_client: redis.Redis, settings: Settings) -> None:
        self.redis = redis_client
        self.settings = settings

    async def dispatch_to_fullsend(self, decision: Decision) -> None:
        """Send experiment request to FULLSEND.

        Publishes to fullsend:to_fullsend channel with:
        - type: "experiment_request"
        - idea: The experiment idea/hypothesis from decision payload
        - context: Relevant context for FULLSEND to design the experiment
        - priority: low/medium/high/urgent
        - requested_at: ISO timestamp
        - orchestrator_reasoning: Why the Orchestrator is dispatching this
        """
        payload = {
            "type": "experiment_request",
            "idea": decision.payload,
            "context": decision.context_for_fullsend or "",
            "priority": decision.priority,
            "requested_at": datetime.now(UTC).isoformat(),
            "orchestrator_reasoning": decision.reasoning,
        }
        await self.redis.publish(
            self.settings.channel_to_fullsend,
            json.dumps(payload),
        )
        logger.info(
            f"Dispatched experiment request to FULLSEND: "
            f"priority={decision.priority}, idea={decision.payload}"
        )

    async def dispatch_to_builder(self, decision: Decision) -> None:
        """Send tool PRD to Builder.

        Publishes to fullsend:builder_tasks channel with:
        - type: "tool_prd"
        - prd: The PRD specification (name, purpose, inputs, outputs)
        - requested_by: "orchestrator"
        - priority: low/medium/high/urgent
        - requested_at: ISO timestamp
        - orchestrator_reasoning: Why the Orchestrator needs this tool
        """
        payload = {
            "type": "tool_prd",
            "prd": decision.payload,
            "requested_by": "orchestrator",
            "priority": decision.priority,
            "requested_at": datetime.now(UTC).isoformat(),
            "orchestrator_reasoning": decision.reasoning,
        }
        await self.redis.publish(
            self.settings.channel_builder_tasks,
            json.dumps(payload),
        )
        logger.info(
            f"Dispatched tool PRD to Builder: "
            f"priority={decision.priority}, prd={decision.payload}"
        )

    async def respond_to_discord(
        self, decision: Decision, original_msg: dict[str, Any]
    ) -> None:
        """Send response back to Discord.

        Publishes to fullsend:from_orchestrator channel with:
        - type: "orchestrator_response"
        - channel_id: Discord channel to respond in
        - content: The message content to send
        - reply_to: Original message ID (if available) for threading
        - priority: For message queue ordering
        """
        payload = {
            "type": "orchestrator_response",
            "channel_id": original_msg.get("channel_id"),
            "content": decision.payload.get("content", ""),
            "reply_to": original_msg.get("message_id"),
            "priority": decision.priority,
        }
        await self.redis.publish(
            self.settings.channel_from_orchestrator,
            json.dumps(payload),
        )
        logger.info(
            f"Sent response to Discord: "
            f"channel={original_msg.get('channel_id')}, "
            f"content_length={len(decision.payload.get('content', ''))}"
        )

    async def kill_experiment(self, decision: Decision) -> None:
        """Archive a failing experiment.

        Sets the experiment state to "archived" in Redis and records:
        - state: "archived"
        - archived_at: ISO timestamp
        - archived_reason: Why the experiment was killed
        - archived_by: "orchestrator"
        """
        if not decision.experiment_id:
            logger.warning("kill_experiment called without experiment_id")
            return

        experiment_key = f"experiments:{decision.experiment_id}"
        reason = decision.payload.get("reason", decision.reasoning)

        # Update experiment hash with archive info
        await self.redis.hset(
            experiment_key,
            mapping={
                "state": "archived",
                "archived_at": datetime.now(UTC).isoformat(),
                "archived_reason": reason,
                "archived_by": "orchestrator",
            },
        )

        logger.info(
            f"Killed experiment: {decision.experiment_id}, reason: {reason}"
        )

    async def initiate_roundtable(self, decision: Decision) -> dict[str, Any]:
        """Trigger a Roundtable session.

        Calls the Roundtable service as a subprocess with:
        - prompt: The question or topic for debate
        - context: Relevant context for the personas
        - learnings: Recent strategic learnings to seed the debate

        Returns the Roundtable result with transcript and summary.
        Per PRD_ROUNDTABLE.md, Roundtable is called as a subprocess, not via Redis.
        """
        prompt = decision.payload.get("prompt", decision.payload.get("topic", ""))
        context = decision.payload.get("context", "")
        learnings = decision.payload.get("learnings", "")

        if not prompt:
            logger.warning("initiate_roundtable called without prompt")
            return {"error": "No prompt provided", "transcript": [], "summary": ""}

        # Prepare input for Roundtable subprocess
        roundtable_input = json.dumps({
            "prompt": prompt,
            "context": context,
            "learnings": learnings,
        })

        logger.info(f"Initiating Roundtable: prompt='{prompt[:100]}...'")

        try:
            # Run Roundtable as subprocess (per PRD_ROUNDTABLE.md)
            # Uses asyncio.to_thread to not block the event loop
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    self._run_roundtable_subprocess,
                    roundtable_input,
                ),
                timeout=self.settings.roundtable_timeout_seconds,
            )
            logger.info(
                f"Roundtable completed: "
                f"transcript_length={len(result.get('transcript', []))}, "
                f"summary_length={len(result.get('summary', ''))}"
            )
            return result

        except asyncio.TimeoutError:
            logger.error(
                f"Roundtable timed out after {self.settings.roundtable_timeout_seconds}s"
            )
            return {
                "error": "Roundtable timed out",
                "transcript": [],
                "summary": "",
            }
        except Exception as e:
            logger.error(f"Roundtable failed: {e}", exc_info=True)
            return {
                "error": str(e),
                "transcript": [],
                "summary": "",
            }

    def _run_roundtable_subprocess(self, input_json: str) -> dict[str, Any]:
        """Run Roundtable as a subprocess (blocking, called in thread).

        Args:
            input_json: JSON string with prompt, context, learnings

        Returns:
            Parsed JSON output from Roundtable with transcript and summary
        """
        env = {
            "ROUNDTABLE_MAX_ROUNDS": str(self.settings.roundtable_max_rounds),
        }

        try:
            result = subprocess.run(
                ["python", "-m", "services.roundtable.main"],
                input=input_json,
                capture_output=True,
                text=True,
                timeout=self.settings.roundtable_timeout_seconds,
                env={**env},
            )

            if result.returncode != 0:
                logger.error(f"Roundtable subprocess error: {result.stderr}")
                return {
                    "error": result.stderr,
                    "transcript": [],
                    "summary": "",
                }

            # Parse JSON output
            return json.loads(result.stdout)

        except subprocess.TimeoutExpired:
            raise asyncio.TimeoutError("Roundtable subprocess timed out")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Roundtable output: {e}")
            return {
                "error": f"Invalid JSON output: {e}",
                "transcript": [],
                "summary": "",
            }

    async def do_update_worklist(self, decision: Decision) -> None:
        """Update worklist.md with new priorities.

        Expects payload with:
        - content: The new worklist content (full or partial)
        - or the payload itself is the worklist content string

        The worklist file is overwritten with the new content.
        """
        # Extract content from payload
        if isinstance(decision.payload, str):
            content = decision.payload
        else:
            content = decision.payload.get(
                "content",
                decision.payload.get("worklist", str(decision.payload)),
            )

        await update_worklist(content, self.settings)
        logger.info(
            f"Updated worklist.md: "
            f"content_length={len(content)}, "
            f"preview='{content[:100]}...'"
        )

    async def do_record_learning(self, decision: Decision) -> None:
        """Append a new strategic learning to learnings.md.

        Expects payload with:
        - learning: The learning/insight to record
        - or content: The learning/insight to record
        - or the payload itself is the learning string

        A timestamp header is automatically added.
        """
        # Extract learning from payload
        if isinstance(decision.payload, str):
            learning = decision.payload
        else:
            learning = decision.payload.get(
                "learning",
                decision.payload.get(
                    "insight",
                    decision.payload.get("content", str(decision.payload)),
                ),
            )

        await append_learning(learning, self.settings)
        logger.info(f"Recorded learning: '{learning[:100]}...'")


async def execute_decision(
    decision: Decision,
    original_msg: dict[str, Any],
    dispatcher: Dispatcher,
) -> dict[str, Any] | None:
    """Execute a decision by routing to the appropriate dispatcher method.

    Args:
        decision: The parsed Decision from the Orchestrator agent
        original_msg: The original message that triggered this decision
        dispatcher: The Dispatcher instance with Redis client

    Returns:
        Result dict for actions that return data (e.g., initiate_roundtable),
        or None for actions that just publish/write.

    Action routing:
        - dispatch_to_fullsend -> Publish experiment request to FULLSEND
        - dispatch_to_builder -> Publish tool PRD to Builder
        - respond_to_discord -> Publish response to Discord
        - update_worklist -> Update worklist.md file
        - record_learning -> Append to learnings.md file
        - kill_experiment -> Archive experiment in Redis
        - initiate_roundtable -> Run Roundtable subprocess
        - no_action -> Log and return (no side effects)
    """
    action = decision.action
    logger.info(
        f"Executing decision: action={action}, "
        f"priority={decision.priority}, "
        f"reasoning='{decision.reasoning[:100]}...'"
    )

    if action == "dispatch_to_fullsend":
        await dispatcher.dispatch_to_fullsend(decision)
        return None

    elif action == "dispatch_to_builder":
        await dispatcher.dispatch_to_builder(decision)
        return None

    elif action == "respond_to_discord":
        await dispatcher.respond_to_discord(decision, original_msg)
        return None

    elif action == "update_worklist":
        await dispatcher.do_update_worklist(decision)
        return None

    elif action == "record_learning":
        await dispatcher.do_record_learning(decision)
        return None

    elif action == "kill_experiment":
        await dispatcher.kill_experiment(decision)
        return None

    elif action == "initiate_roundtable":
        result = await dispatcher.initiate_roundtable(decision)
        return result

    elif action == "no_action":
        logger.info(f"No action taken: {decision.reasoning}")
        return None

    else:
        logger.warning(f"Unknown action '{action}', ignoring")
        return None
