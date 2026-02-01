"""Simple response generation for messages Watcher can answer directly.

Reads Redis keys (status, experiment counts, recent activity) to answer
simple queries without escalating to Orchestrator.

Watcher can READ (not write) these keys:
- fullsend:status - System status ("running" | "paused")
- experiments:* - Experiment definitions (to count active)
- fullsend:recent_runs - Recent activity log
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

import google.generativeai as genai
import redis.asyncio as redis

from .classifier import Classification
from .retry import ModelCallError, retry_model_call

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(filename: str) -> str:
    """Load a prompt template from the prompts directory."""
    prompt_path = PROMPTS_DIR / filename
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    return prompt_path.read_text()


async def get_system_status(redis_client: redis.Redis) -> dict[str, Any]:
    """Read system status from Redis for answering queries.

    Watcher can READ these keys (not write):
    - fullsend:status - System status ("running" | "paused")
    - experiments:* - Experiment definitions (to count active)
    - fullsend:recent_runs - Recent activity log

    Returns:
        Dictionary with status info:
        - status: "running" | "paused" | "unknown"
        - total_experiments: int
        - active_experiments: int
        - recent_runs: list of recent activity entries
    """
    status_info: dict[str, Any] = {}

    try:
        # Get system status
        status = await redis_client.get("fullsend:status")
        status_info["status"] = status or "unknown"

        # Count experiments
        experiment_keys = await redis_client.keys("experiments:*")
        active_count = 0
        total_count = 0
        for key in experiment_keys:
            key_type = await redis_client.type(key)
            if key_type == "hash":
                state = await redis_client.hget(key, "state")
                if state == "running":
                    active_count += 1
                total_count += 1
        status_info["total_experiments"] = total_count
        status_info["active_experiments"] = active_count

        # Get recent activity (last 5 items)
        recent = await redis_client.lrange("fullsend:recent_runs", 0, 4)
        status_info["recent_runs"] = recent or []

    except Exception as e:
        logger.error(f"Error reading Redis status: {e}")
        status_info["error"] = str(e)

    return status_info


async def _call_gemini_response(
    model: Any,
    prompt: str,
    generation_config: Any,
) -> str:
    """Make the actual Gemini API call for response generation.

    Separated out to allow retry wrapping.
    """
    response = await asyncio.to_thread(
        model.generate_content,
        prompt,
        generation_config=generation_config,
    )
    return response.text


def format_recent_activity(recent_runs: list[str]) -> str:
    """Format recent activity for prompt context.

    Args:
        recent_runs: List of recent run entries (may be JSON strings)

    Returns:
        Human-readable summary of recent activity
    """
    if not recent_runs:
        return "No recent activity"

    summaries = []
    for entry in recent_runs[:3]:  # Limit to 3 most recent
        try:
            if isinstance(entry, str) and entry.startswith("{"):
                data = json.loads(entry)
                summary = data.get("summary", data.get("type", "activity"))
                summaries.append(f"- {summary}")
            else:
                summaries.append(f"- {entry}")
        except (json.JSONDecodeError, TypeError):
            summaries.append(f"- {entry}")

    return "\n".join(summaries) if summaries else "No recent activity"


async def generate_response(
    msg: dict[str, Any],
    classification: Classification,
    redis_client: redis.Redis,
    settings: Any,
) -> str:
    """Generate a simple response for queries Watcher can handle.

    Uses Redis data (status, experiment counts, recent activity) to answer
    simple queries like "What's the status?" or "How many experiments?"
    Uses retry logic with exponential backoff for model calls.

    Args:
        msg: Original Discord message
        classification: Classification result with suggested_response
        redis_client: Redis client for reading status
        settings: Application settings

    Returns:
        Response string to send back to Discord

    Raises:
        ModelCallError: If all retry attempts fail
    """
    # If classifier already provided a suggested response, use it directly
    if classification.suggested_response:
        return classification.suggested_response

    # Otherwise, generate a response using current system state
    genai.configure(api_key=settings.google_api_key)

    # Get current system status from Redis
    status_info = await get_system_status(redis_client)
    logger.info(
        f"Redis status: {status_info.get('status')}, "
        f"experiments: {status_info.get('active_experiments')}/{status_info.get('total_experiments')}"
    )

    # Format recent activity for prompt
    recent_activity = format_recent_activity(status_info.get("recent_runs", []))

    # Load and format prompt with all available data
    prompt_template = load_prompt("respond.txt")
    prompt = prompt_template.replace("{{query}}", msg.get("content", ""))
    prompt = prompt.replace("{{status}}", status_info.get("status", "unknown"))
    prompt = prompt.replace(
        "{{experiment_count}}",
        str(status_info.get("active_experiments", 0))
    )
    prompt = prompt.replace(
        "{{total_experiments}}",
        str(status_info.get("total_experiments", 0))
    )
    prompt = prompt.replace("{{recent_activity}}", recent_activity)

    # Call Gemini model with retry logic
    model = genai.GenerativeModel(settings.watcher_model)
    generation_config = genai.GenerationConfig(
        temperature=settings.response_temperature,
        max_output_tokens=settings.response_max_tokens,
    )

    response_text = await retry_model_call(
        _call_gemini_response,
        model,
        prompt,
        generation_config,
        max_attempts=settings.model_retry_attempts,
        base_delay=settings.model_retry_base_delay,
        max_delay=settings.model_retry_max_delay,
    )

    return response_text.strip()


async def _test_responder() -> None:
    """CLI test for responder - read JSON from stdin, generate response."""
    from .config import get_settings

    logging.basicConfig(level=logging.INFO)

    # Read test input from stdin
    input_data = sys.stdin.read().strip()
    if not input_data:
        print("Usage: echo '{\"content\": \"status?\"}' | python -m services.watcher.responder")
        sys.exit(1)

    try:
        msg = json.loads(input_data)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        sys.exit(1)

    # Create mock classification for testing
    mock_classification = Classification(
        action="answer",
        reason="Test query",
        priority="low",
        suggested_response=None,
    )

    settings = get_settings()

    # Connect to Redis
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)

    try:
        # Get status info
        status_info = await get_system_status(redis_client)
        print("Redis Status:")
        print(json.dumps(status_info, indent=2, default=str))
        print()

        # Generate response
        response = await generate_response(msg, mock_classification, redis_client, settings)
        print("Generated Response:")
        print(response)
    finally:
        await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(_test_responder())
