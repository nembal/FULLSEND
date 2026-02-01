"""Main entry point for Orchestrator service - daemon loop for strategic decisions."""

import asyncio
import json
import logging
from typing import Any

import redis.asyncio as redis

from .agent import OrchestratorAgent
from .config import get_settings
from .context import Context, append_learning, load_context, update_worklist
from .dispatcher import Decision, Dispatcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Timeout for context loading (should be fast, but handle Redis slowness)
CONTEXT_LOAD_TIMEOUT_SECONDS = 30

# Timeout for executing a decision (most are fast, but Roundtable can take longer)
DECISION_EXECUTE_TIMEOUT_SECONDS = 180


async def load_context_safe(
    redis_client: redis.Redis, settings: Any
) -> Context:
    """Load context with timeout and safe fallbacks.

    Args:
        redis_client: Redis client for fetching experiments/tools/metrics
        settings: Application settings

    Returns:
        Context object with all available data. On timeout or error,
        returns an empty context with logged warning.
    """
    try:
        return await asyncio.wait_for(
            load_context(redis_client, settings),
            timeout=CONTEXT_LOAD_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning(
            f"Context loading timed out after {CONTEXT_LOAD_TIMEOUT_SECONDS}s, "
            "using empty context"
        )
        return Context(
            product="",
            worklist="",
            learnings="",
            active_experiments=[],
            available_tools=[],
            recent_metrics={},
        )
    except Exception as e:
        logger.error(f"Error loading context: {e}", exc_info=True)
        return Context(
            product="",
            worklist="",
            learnings="",
            active_experiments=[],
            available_tools=[],
            recent_metrics={},
        )


async def execute_decision(
    decision: Decision,
    msg: dict[str, Any],
    context: Context,
    dispatcher: Dispatcher,
    settings: Any,
) -> dict[str, Any] | None:
    """Execute the Orchestrator's decision.

    Returns:
        For initiate_roundtable: Returns the Roundtable result (transcript + summary)
        For other actions: Returns None
    """
    logger.info(f"Executing decision: action={decision.action}, priority={decision.priority}")

    if decision.action == "dispatch_to_fullsend":
        await dispatcher.dispatch_to_fullsend(decision)

    elif decision.action == "dispatch_to_builder":
        await dispatcher.dispatch_to_builder(decision)

    elif decision.action == "respond_to_discord":
        await dispatcher.respond_to_discord(decision, msg)

    elif decision.action == "update_worklist":
        content = decision.payload.get("content", "")
        if content:
            await update_worklist(content, settings)
        else:
            logger.warning("update_worklist called without content")

    elif decision.action == "record_learning":
        learning = decision.payload.get("learning", "")
        if learning:
            await append_learning(learning, settings)
        else:
            logger.warning("record_learning called without learning content")

    elif decision.action == "kill_experiment":
        await dispatcher.kill_experiment(decision)

    elif decision.action == "initiate_roundtable":
        result = await dispatcher.initiate_roundtable(decision)
        # Log the summary for visibility
        if result.get("summary"):
            logger.info(f"Roundtable summary: {result['summary'][:200]}...")
        return result

    elif decision.action == "no_action":
        logger.info(f"No action taken: {decision.reasoning}")

    return None


async def execute_decision_safe(
    decision: Decision,
    msg: dict[str, Any],
    context: Context,
    dispatcher: Dispatcher,
    settings: Any,
) -> dict[str, Any] | None:
    """Execute decision with timeout and error handling.

    Wraps execute_decision with a timeout to prevent hung operations.

    Args:
        decision: The decision to execute
        msg: Original message
        context: Current context
        dispatcher: Dispatcher instance
        settings: Application settings

    Returns:
        Result dict for actions that return data, or None.
        On timeout or error, returns None and logs the error.
    """
    try:
        return await asyncio.wait_for(
            execute_decision(decision, msg, context, dispatcher, settings),
            timeout=DECISION_EXECUTE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.error(
            f"Decision execution timed out after {DECISION_EXECUTE_TIMEOUT_SECONDS}s "
            f"for action={decision.action}"
        )
        return None
    except redis.RedisError as e:
        logger.error(f"Redis error during decision execution: {e}")
        return None
    except Exception as e:
        logger.error(
            f"Error executing decision action={decision.action}: {e}", exc_info=True
        )
        return None


async def process_message(
    msg: dict[str, Any],
    agent: OrchestratorAgent,
    dispatcher: Dispatcher,
    redis_client: redis.Redis,
    settings: Any,
) -> None:
    """Process a single message through the Orchestrator.

    Handles the full flow: context loading -> thinking -> decision execution.
    All stages have proper timeout and error handling.

    Args:
        msg: The incoming message to process
        agent: OrchestratorAgent instance for decision-making
        dispatcher: Dispatcher instance for executing decisions
        redis_client: Redis client for context loading
        settings: Application settings
    """
    msg_type = msg.get("type", "unknown")
    msg_source = msg.get("source", "unknown")
    logger.info(f"Processing message: {msg_type} from {msg_source}")

    # Load fresh context with timeout
    context = await load_context_safe(redis_client, settings)

    # Get decision from agent with extended thinking (has its own timeout)
    decision = await agent.process_with_thinking(msg, context)

    # Execute the decision with timeout
    result = await execute_decision_safe(decision, msg, context, dispatcher, settings)

    # Log Roundtable result if applicable
    if result and decision.action == "initiate_roundtable":
        summary = result.get("summary", "")
        if summary:
            logger.info(f"Roundtable completed: {summary[:200]}...")


async def main() -> None:
    """Main daemon loop - subscribe to messages and process them.

    Includes reconnection logic for Redis failures and graceful shutdown.
    """
    settings = get_settings()
    logger.info("Starting Orchestrator service...")
    logger.info(f"Model: {settings.orchestrator_model}")
    logger.info(f"Thinking budget: {settings.orchestrator_thinking_budget} tokens")
    logger.info(f"Thinking timeout: {settings.thinking_timeout_seconds}s")
    logger.info(f"Redis: {settings.redis_url}")

    # Initialize components
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    agent = OrchestratorAgent(settings)
    dispatcher = Dispatcher(redis_client, settings)
    pubsub = redis_client.pubsub()

    # Reconnection state
    reconnect_delay = 1  # Start with 1 second
    max_reconnect_delay = 60  # Cap at 60 seconds
    consecutive_errors = 0
    max_consecutive_errors = 10  # Log warning after this many

    try:
        await pubsub.subscribe(settings.channel_to_orchestrator)
        logger.info(f"Subscribed to {settings.channel_to_orchestrator}")

        # Load initial context with safe fallback
        context = await load_context_safe(redis_client, settings)
        logger.info("Initial context loaded")

        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    await process_message(data, agent, dispatcher, redis_client, settings)
                    # Reset error counter on success
                    consecutive_errors = 0
                    reconnect_delay = 1
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse message: {e}")
                    # JSON errors are likely bad data, not system issues
                except redis.RedisError as e:
                    consecutive_errors += 1
                    logger.error(
                        f"Redis error (attempt {consecutive_errors}): {e}"
                    )
                    if consecutive_errors >= max_consecutive_errors:
                        logger.warning(
                            f"Hit {max_consecutive_errors} consecutive Redis errors. "
                            "Redis may be unhealthy."
                        )
                    # Wait before processing next message
                    await asyncio.sleep(min(reconnect_delay, max_reconnect_delay))
                    reconnect_delay *= 2  # Exponential backoff
                except Exception as e:
                    consecutive_errors += 1
                    logger.error(
                        f"Error processing message (attempt {consecutive_errors}): {e}",
                        exc_info=True,
                    )
                    if consecutive_errors >= max_consecutive_errors:
                        logger.warning(
                            f"Hit {max_consecutive_errors} consecutive errors. "
                            "System may be unhealthy."
                        )

    except KeyboardInterrupt:
        logger.info("Shutting down Orchestrator...")
    except redis.RedisError as e:
        logger.error(f"Fatal Redis error: {e}")
    finally:
        try:
            await pubsub.unsubscribe(settings.channel_to_orchestrator)
            await redis_client.aclose()
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")
        logger.info("Orchestrator stopped")


if __name__ == "__main__":
    asyncio.run(main())
