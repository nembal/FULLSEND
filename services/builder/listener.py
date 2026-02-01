"""Builder Listener - bridges Redis to Claude Code.

Subscribes to fullsend:builder_tasks, writes PRDs to current_prd.yaml,
spawns Claude Code (run.sh), reports back to Redis.

Usage:
    uv run python -m services.builder.listener
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import redis.asyncio as redis
import yaml

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Paths
SERVICE_DIR = Path(__file__).parent
REQUESTS_DIR = SERVICE_DIR / "requests"
CURRENT_PRD = REQUESTS_DIR / "current_prd.yaml"
RUN_SH = SERVICE_DIR / "run.sh"

# Redis config
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
CHANNEL_BUILDER_TASKS = "fullsend:builder_tasks"
CHANNEL_BUILDER_RESULTS = "fullsend:builder_results"
CHANNEL_TO_ORCHESTRATOR = "fullsend:to_orchestrator"

# Execution timeout (Claude Code can take a while for complex tools)
EXECUTION_TIMEOUT = int(os.getenv("BUILDER_TIMEOUT", "900"))  # 15 minutes default


async def write_prd(request: dict) -> Path:
    """Write incoming PRD to current_prd.yaml."""
    prd = request.get("prd", {})
    requested_by = request.get("requested_by", "unknown")
    priority = request.get("priority", "medium")
    reasoning = request.get("orchestrator_reasoning", "")
    
    # Build the YAML structure
    prd_content = {
        "prd": {
            **prd,
            "_meta": {
                "requested_by": requested_by,
                "priority": priority,
                "received_at": datetime.now(UTC).isoformat(),
                "orchestrator_reasoning": reasoning,
            }
        }
    }
    
    # Write to file
    REQUESTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(CURRENT_PRD, "w") as f:
        yaml.dump(prd_content, f, default_flow_style=False, sort_keys=False)
    
    logger.info(f"Wrote PRD to {CURRENT_PRD}")
    return CURRENT_PRD


async def run_builder() -> dict:
    """Run Builder Claude Code and capture result."""
    try:
        logger.info("Running Builder (run.sh)...")
        result = await asyncio.wait_for(
            asyncio.to_thread(
                _run_subprocess,
                [str(RUN_SH)],
            ),
            timeout=EXECUTION_TIMEOUT,
        )
        
        return {
            "success": result["returncode"] == 0,
            "output": result["stdout"][-2000:] if result["stdout"] else "",
            "error": result["stderr"][-1000:] if result["stderr"] else "",
            "returncode": result["returncode"],
        }
        
    except asyncio.TimeoutError:
        logger.error(f"Builder timed out after {EXECUTION_TIMEOUT}s")
        return {
            "success": False,
            "error": f"Execution timed out after {EXECUTION_TIMEOUT}s",
            "returncode": -1,
        }
    except Exception as e:
        logger.error(f"Builder failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "returncode": -1,
        }


def _run_subprocess(cmd: list) -> dict:
    """Run subprocess and capture output (blocking, called in thread)."""
    logger.info(f"Executing: {' '.join(cmd)}")
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=SERVICE_DIR,
        timeout=EXECUTION_TIMEOUT,
    )
    
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
    }


async def publish_result(
    redis_client: redis.Redis,
    channel: str,
    msg_type: str,
    payload: dict,
) -> None:
    """Publish result to Redis channel."""
    message = {
        "type": msg_type,
        "source": "builder_listener",
        "timestamp": datetime.now(UTC).isoformat(),
        **payload,
    }
    await redis_client.publish(channel, json.dumps(message))
    logger.info(f"Published to {channel}: {msg_type}")


async def process_request(
    request: dict,
    redis_client: redis.Redis,
) -> None:
    """Process a single Builder request."""
    prd = request.get("prd", {})
    # Support both "name" and "tool_name" keys (Orchestrator uses "tool_name")
    tool_name = prd.get("name") or prd.get("tool_name", "unknown")
    request_id = request.get("request_id", datetime.now(UTC).strftime("%Y%m%d_%H%M%S"))
    
    logger.info(f"Processing PRD: {tool_name} (request: {request_id})")
    
    # Notify start
    await publish_result(redis_client, CHANNEL_TO_ORCHESTRATOR, "builder_started", {
        "request_id": request_id,
        "tool_name": tool_name,
    })
    
    # Write PRD to file
    await write_prd(request)
    
    # Run Builder
    result = await run_builder()
    
    # Notify completion
    if result["success"]:
        await publish_result(redis_client, CHANNEL_BUILDER_RESULTS, "tool_built", {
            "request_id": request_id,
            "tool_name": tool_name,
            "output_preview": result.get("output", "")[:500],
        })
        await publish_result(redis_client, CHANNEL_TO_ORCHESTRATOR, "builder_completed", {
            "request_id": request_id,
            "tool_name": tool_name,
        })
        logger.info(f"Tool built successfully: {tool_name}")
    else:
        await publish_result(redis_client, CHANNEL_BUILDER_RESULTS, "tool_build_failed", {
            "request_id": request_id,
            "tool_name": tool_name,
            "error": result.get("error", "Unknown error"),
        })
        await publish_result(redis_client, CHANNEL_TO_ORCHESTRATOR, "builder_failed", {
            "request_id": request_id,
            "tool_name": tool_name,
            "error": result.get("error", "Unknown error"),
        })
        logger.error(f"Tool build failed: {tool_name} - {result.get('error')}")


async def main() -> None:
    """Main listener loop."""
    logger.info("=" * 60)
    logger.info("Starting Builder Listener")
    logger.info("=" * 60)
    logger.info(f"Redis: {REDIS_URL}")
    logger.info(f"Channel: {CHANNEL_BUILDER_TASKS}")
    logger.info(f"Timeout: {EXECUTION_TIMEOUT}s")
    logger.info(f"Service dir: {SERVICE_DIR}")
    logger.info("=" * 60)
    
    # Connect to Redis
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    pubsub = redis_client.pubsub()
    
    try:
        # Test connection
        await redis_client.ping()
        logger.info("Connected to Redis")
        
        # Subscribe
        await pubsub.subscribe(CHANNEL_BUILDER_TASKS)
        logger.info(f"Subscribed to {CHANNEL_BUILDER_TASKS}")
        logger.info("Waiting for PRDs...")
        
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    await process_request(data, redis_client)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse message: {e}")
                except Exception as e:
                    logger.error(f"Error processing request: {e}", exc_info=True)
                    
    except KeyboardInterrupt:
        logger.info("Shutting down Builder Listener...")
    finally:
        await pubsub.unsubscribe(CHANNEL_BUILDER_TASKS)
        await redis_client.aclose()
        logger.info("Builder Listener stopped")


if __name__ == "__main__":
    asyncio.run(main())
