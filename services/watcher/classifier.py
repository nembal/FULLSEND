"""Message classification logic using Google Gemini."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Literal, Optional

import google.generativeai as genai
from pydantic import BaseModel

from .retry import ModelCallError, retry_model_call

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


class Classification(BaseModel):
    """Result of message classification."""

    action: Literal["ignore", "answer", "escalate"]
    reason: str
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    suggested_response: Optional[str] = None


def load_prompt(filename: str) -> str:
    """Load a prompt template from the prompts directory."""
    prompt_path = PROMPTS_DIR / filename
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    return prompt_path.read_text()


def parse_classification(response_text: str) -> Classification:
    """Parse LLM response into Classification object.

    Handles various response formats:
    - Raw JSON
    - JSON in markdown code blocks (```json or ```)
    - JSON with surrounding text

    On parse failure, defaults to escalate for safety.
    """
    text = response_text.strip()

    # Handle markdown code blocks
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    # Try to find JSON object if there's surrounding text
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            text = text[start:end]

    try:
        data = json.loads(text)

        # Validate action is one of the expected values
        action = data.get("action", "escalate")
        if action not in ("ignore", "answer", "escalate"):
            logger.warning(f"Invalid action '{action}', defaulting to escalate")
            action = "escalate"

        # Validate priority is one of the expected values
        priority = data.get("priority", "medium")
        if priority not in ("low", "medium", "high", "urgent"):
            logger.warning(f"Invalid priority '{priority}', defaulting to medium")
            priority = "medium"

        return Classification(
            action=action,
            reason=data.get("reason", "No reason provided"),
            priority=priority,
            suggested_response=data.get("suggested_response"),
        )
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning(f"Failed to parse classification response: {e}. Raw text: {response_text[:200]}")
        # Default to escalate when parsing fails - better safe than sorry
        return Classification(
            action="escalate",
            reason="Classification parsing failed - escalating for safety",
            priority="medium",
        )


async def _call_gemini_classify(
    model: Any,
    prompt: str,
    generation_config: Any,
) -> str:
    """Make the actual Gemini API call for classification.

    Separated out to allow retry wrapping.
    """
    response = await asyncio.to_thread(
        model.generate_content,
        prompt,
        generation_config=generation_config,
    )
    return response.text


async def classify(msg: dict[str, Any], settings: Any) -> Classification:
    """Classify a Discord message using Gemini.

    Uses retry logic with exponential backoff for model calls.

    Args:
        msg: The Discord message dict with keys like username, content, channel_name, mentions_bot
        settings: Application settings with model config

    Returns:
        Classification result with action, reason, priority, and optional suggested_response

    Raises:
        ModelCallError: If all retry attempts fail
    """
    # Configure Gemini API
    genai.configure(api_key=settings.google_api_key)

    # Load and format prompt
    prompt_template = load_prompt("classify.txt")
    prompt = prompt_template.replace("{{username}}", msg.get("username", "unknown"))
    prompt = prompt.replace("{{channel}}", msg.get("channel_name", "unknown"))
    prompt = prompt.replace("{{has_mention}}", str(msg.get("mentions_bot", False)))
    prompt = prompt.replace("{{content}}", msg.get("content", ""))

    # Call Gemini model with retry logic
    model = genai.GenerativeModel(settings.watcher_model)
    generation_config = genai.GenerationConfig(
        temperature=settings.classification_temperature,
        max_output_tokens=settings.classification_max_tokens,
    )

    response_text = await retry_model_call(
        _call_gemini_classify,
        model,
        prompt,
        generation_config,
        max_attempts=settings.model_retry_attempts,
        base_delay=settings.model_retry_base_delay,
        max_delay=settings.model_retry_max_delay,
    )

    logger.debug(f"Gemini response: {response_text}")
    return parse_classification(response_text)


# Allow running classifier directly for testing
if __name__ == "__main__":
    import sys

    from .config import get_settings

    if sys.stdin.isatty():
        print("Usage: echo '{\"content\": \"test\", \"username\": \"user\"}' | python -m services.watcher.classifier")
        sys.exit(1)

    input_data = json.loads(sys.stdin.read())
    settings = get_settings()
    result = asyncio.run(classify(input_data, settings))
    print(result.model_dump_json(indent=2))
