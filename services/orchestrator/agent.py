"""Core agent logic for Orchestrator with extended thinking."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Literal

import anthropic

from .config import PROMPTS_DIR, Settings
from .context import Context
from .dispatcher import Decision

logger = logging.getLogger(__name__)


class ThinkingTimeoutError(Exception):
    """Raised when extended thinking takes too long."""

    pass

# Valid action types for strict parsing
VALID_ACTIONS: set[str] = {
    "dispatch_to_fullsend",
    "dispatch_to_builder",
    "respond_to_discord",
    "update_worklist",
    "record_learning",
    "kill_experiment",
    "initiate_roundtable",
    "no_action",
}

# Valid priority levels for strict parsing
VALID_PRIORITIES: set[str] = {"low", "medium", "high", "urgent"}


def load_prompt(filename: str) -> str:
    """Load a prompt template from the prompts directory."""
    path = PROMPTS_DIR / filename
    if not path.exists():
        logger.warning(f"Prompt file not found: {path}")
        return ""
    return path.read_text()


def _format_experiments_summary(experiments: list[dict[str, Any]]) -> str:
    """Format active experiments for the prompt."""
    if not experiments:
        return "(No active experiments)"

    lines = []
    for exp in experiments:
        exp_id = exp.get("id", exp.get("experiment_id", "unknown"))
        state = exp.get("state", "unknown")
        name = exp.get("name", exp.get("summary", "unnamed"))
        lines.append(f"- {exp_id}: {name} (state: {state})")
    return "\n".join(lines)


def _format_metrics_summary(metrics: dict[str, Any]) -> str:
    """Format recent metrics for the prompt."""
    if not metrics:
        return "(No recent metrics)"

    lines = []
    for key, value in metrics.items():
        if isinstance(value, dict):
            metric_str = ", ".join(f"{k}={v}" for k, v in value.items())
            lines.append(f"- {key}: {metric_str}")
        else:
            lines.append(f"- {key}: {value}")
    return "\n".join(lines)


def build_prompt(msg: dict[str, Any], context: Context) -> str:
    """Build the full prompt for the model including all context.

    Formats the incoming message and all context data into a structured
    prompt for strategic decision-making.

    Args:
        msg: The incoming message to process
        context: Current context including product, worklist, learnings, etc.

    Returns:
        Formatted prompt string for the model
    """
    experiments_summary = _format_experiments_summary(context.active_experiments)
    tools_list = ", ".join(context.available_tools) if context.available_tools else "(No tools registered)"
    metrics_summary = _format_metrics_summary(context.recent_metrics)

    prompt = f"""## Incoming Message
Type: {msg.get('type', 'unknown')}
Source: {msg.get('source', 'unknown')}
Priority: {msg.get('priority', 'normal')}

Content:
{json.dumps(msg, indent=2)}

## Current Context

### Product
{context.product or '(No product context available)'}

### Worklist
{context.worklist or '(No worklist available)'}

### Strategic Learnings
{context.learnings or '(No learnings recorded yet)'}

### Active Experiments
{experiments_summary}

### Available Tools
{tools_list}

### Recent Metrics
{metrics_summary}

## Your Task
Analyze this message and decide what action to take. Use your extended thinking to reason through the decision carefully.

Output your decision as a JSON object with the following structure:
```json
{{
  "action": "<action_type>",
  "reasoning": "<brief explanation>",
  "payload": {{ ... }},
  "priority": "<low|medium|high|urgent>"
}}
```

Valid actions: {", ".join(sorted(VALID_ACTIONS))}
"""
    return prompt


def _extract_json_from_text(text: str) -> str:
    """Extract JSON string from model response text.

    Handles both fenced code blocks and raw JSON.
    """
    # Try fenced JSON block first
    if "```json" in text:
        json_start = text.find("```json") + 7
        json_end = text.find("```", json_start)
        if json_end > json_start:
            return text[json_start:json_end].strip()

    # Try raw JSON with balanced brace matching
    if "{" in text:
        start = text.find("{")
        depth = 0
        end = start
        for i, char in enumerate(text[start:], start):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end > start:
            return text[start:end]

    raise ValueError("No JSON found in response")


def _validate_action(action: str) -> str:
    """Validate and normalize action string."""
    action = action.strip().lower()
    if action not in VALID_ACTIONS:
        logger.warning(f"Invalid action '{action}', defaulting to 'no_action'")
        return "no_action"
    return action


def _validate_priority(priority: str) -> str:
    """Validate and normalize priority string."""
    priority = priority.strip().lower()
    if priority not in VALID_PRIORITIES:
        logger.warning(f"Invalid priority '{priority}', defaulting to 'medium'")
        return "medium"
    return priority


def _extract_content_from_response(response: Any) -> tuple[str, str | None]:
    """Extract text and thinking content from extended thinking response.

    Args:
        response: The Anthropic API response object

    Returns:
        Tuple of (text_content, thinking_content)
    """
    text_content = ""
    thinking_content = None

    for block in response.content:
        if block.type == "text":
            text_content = block.text
        elif block.type == "thinking":
            thinking_content = block.thinking

    return text_content, thinking_content


def parse_decision(response: Any) -> Decision:
    """Parse the model's response into a Decision object with strict validation.

    Extracts JSON from the model response (supporting both fenced code blocks
    and raw JSON), validates action and priority fields, and returns a
    properly typed Decision object. Also extracts and logs thinking content
    from extended thinking responses for auditing.

    Args:
        response: The Anthropic API response object

    Returns:
        Decision object with validated fields
    """
    # Extract text content and thinking from response
    text_content, thinking_content = _extract_content_from_response(response)

    # Log thinking content for debugging/auditing (truncated for log size)
    if thinking_content:
        logger.debug(
            f"Extended thinking ({len(thinking_content)} chars):\n"
            f"{thinking_content[:1000]}{'...' if len(thinking_content) > 1000 else ''}"
        )

    if not text_content:
        logger.error("No text content found in response")
        return Decision(
            action="no_action",
            reasoning="No text content in model response",
            payload={},
            priority="low",
        )

    try:
        json_str = _extract_json_from_text(text_content)
        data = json.loads(json_str)

        if not isinstance(data, dict):
            raise ValueError(f"Expected JSON object, got {type(data).__name__}")

        # Strictly validate required fields
        action = _validate_action(data.get("action", "no_action"))
        priority = _validate_priority(data.get("priority", "medium"))

        # Extract reasoning (required for logging)
        reasoning = data.get("reasoning", "")
        if not reasoning:
            logger.warning("Decision missing reasoning field")

        # Extract payload (action-specific data)
        payload = data.get("payload", {})
        if not isinstance(payload, dict):
            logger.warning(f"Payload is not a dict, wrapping: {type(payload)}")
            payload = {"value": payload}

        # Extract optional fields based on action type
        experiment_id = None
        context_for_fullsend = None

        if action == "kill_experiment":
            experiment_id = data.get("experiment_id") or payload.get("experiment_id")
            if not experiment_id:
                logger.warning("kill_experiment action missing experiment_id")

        if action == "dispatch_to_fullsend":
            context_for_fullsend = data.get("context_for_fullsend") or payload.get("context")

        return Decision(
            action=action,
            reasoning=reasoning,
            payload=payload,
            priority=priority,
            experiment_id=experiment_id,
            context_for_fullsend=context_for_fullsend,
        )

    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}")
        return Decision(
            action="no_action",
            reasoning=f"JSON parse error: {e}",
            payload={"raw_response": text_content[:500]},
            priority="low",
        )
    except ValueError as e:
        logger.error(f"Decision validation error: {e}")
        return Decision(
            action="no_action",
            reasoning=f"Validation error: {e}",
            payload={},
            priority="low",
        )


class OrchestratorAgent:
    """The Orchestrator agent with extended thinking capability."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.system_prompt = load_prompt("system.txt")

    async def process_with_thinking(
        self, msg: dict[str, Any], context: Context
    ) -> Decision:
        """Use extended thinking to make strategic decisions.

        This is the core decision-making function. It:
        1. Builds a prompt with full context (message, product, worklist, learnings, etc.)
        2. Calls Claude Opus 4 with extended thinking enabled for deep reasoning
        3. Parses and validates the JSON decision from the response
        4. Logs the decision with reasoning for auditing

        Args:
            msg: The incoming message to process (escalation, alert, completion, etc.)
            context: Current context including product info, worklist, learnings,
                     active experiments, available tools, and recent metrics

        Returns:
            Validated Decision object with action, reasoning, payload, and priority
            On timeout or error, returns a safe fallback Decision
        """
        prompt = build_prompt(msg, context)

        logger.debug(f"Processing message type={msg.get('type')} from source={msg.get('source')}")

        try:
            decision = await asyncio.wait_for(
                self._call_model_with_thinking(prompt),
                timeout=self.settings.thinking_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.error(
                f"Orchestrator thinking timed out after {self.settings.thinking_timeout_seconds}s "
                f"for message type={msg.get('type')}"
            )
            # Return fallback decision per PRD error handling
            return self._create_timeout_fallback(msg)
        except anthropic.APIConnectionError as e:
            logger.error(f"API connection error: {e}")
            return self._create_api_error_fallback(msg, "connection_error", str(e))
        except anthropic.RateLimitError as e:
            logger.error(f"API rate limit error: {e}")
            return self._create_api_error_fallback(msg, "rate_limit", str(e))
        except anthropic.APIStatusError as e:
            logger.error(f"API status error: {e.status_code} - {e.message}")
            return self._create_api_error_fallback(msg, f"api_error_{e.status_code}", e.message)
        except Exception as e:
            logger.error(f"Unexpected error during thinking: {e}", exc_info=True)
            return self._create_api_error_fallback(msg, "unexpected_error", str(e))

        # Log decision with context for auditing
        logger.info(
            f"Decision: action={decision.action} priority={decision.priority} | "
            f"reasoning: {decision.reasoning[:100]}{'...' if len(decision.reasoning) > 100 else ''}"
        )

        return decision

    async def _call_model_with_thinking(self, prompt: str) -> Decision:
        """Call the model with extended thinking and parse the response.

        This is a separate method to allow asyncio.wait_for to wrap it cleanly.

        Args:
            prompt: The full prompt to send to the model

        Returns:
            Parsed Decision object
        """
        response = await self.client.messages.create(
            model=self.settings.orchestrator_model,
            max_tokens=self.settings.orchestrator_max_tokens,
            thinking={
                "type": "enabled",
                "budget_tokens": self.settings.orchestrator_thinking_budget,
            },
            system=self.system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        return parse_decision(response)

    def _create_timeout_fallback(self, msg: dict[str, Any]) -> Decision:
        """Create a fallback decision when thinking times out.

        Per PRD: respond to Discord that we're still thinking.

        Args:
            msg: The original message that timed out

        Returns:
            Decision to respond to Discord with a "still thinking" message
        """
        return Decision(
            action="respond_to_discord",
            reasoning=f"Thinking timed out after {self.settings.thinking_timeout_seconds}s. "
            "Sending acknowledgment to user.",
            payload={
                "content": "I'm still thinking about this. Will update soon.",
            },
            priority="medium",
        )

    def _create_api_error_fallback(
        self, msg: dict[str, Any], error_type: str, error_message: str
    ) -> Decision:
        """Create a fallback decision when an API error occurs.

        Args:
            msg: The original message that caused the error
            error_type: Type of error (e.g., 'rate_limit', 'connection_error')
            error_message: The error message

        Returns:
            Decision with no_action but logged error context
        """
        return Decision(
            action="no_action",
            reasoning=f"API error ({error_type}): {error_message[:200]}. "
            "Will retry on next message cycle.",
            payload={
                "error_type": error_type,
                "error_message": error_message[:500],
                "original_message_type": msg.get("type"),
                "original_source": msg.get("source"),
            },
            priority="low",
        )
