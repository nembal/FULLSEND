#!/usr/bin/env python3
"""
Tool Registration Script

Registers tools in Redis for the Executor service to discover and execute.
Can be used standalone or as a module.

Usage:
    # Register a single tool
    python -m tools.register browserbase

    # Register all tools in the tools directory
    python -m tools.register --all

    # Check registration status
    python -m tools.register --status browserbase

Environment Variables:
    REDIS_URL: Redis connection URL (default: redis://localhost:6379)
"""

import argparse
import asyncio
import importlib.util
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Tool metadata registry - add new tools here
TOOL_REGISTRY = {
    "browserbase": {
        "name": "browserbase",
        "description": "Web research and scraping via Browserbase cloud browser",
        "path": "tools/browserbase.py",
    },
}


async def get_redis_client():
    """Get async Redis client."""
    try:
        import redis.asyncio as redis
    except ImportError:
        print("Error: redis package not installed. Install with: pip install redis")
        sys.exit(1)

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    return redis.from_url(redis_url, decode_responses=True)


async def register_tool(tool_name: str, dry_run: bool = False) -> bool:
    """Register a tool in Redis.

    Args:
        tool_name: Name of the tool to register
        dry_run: If True, only print what would be done

    Returns:
        True if registration succeeded
    """
    if tool_name not in TOOL_REGISTRY:
        print(f"Error: Unknown tool '{tool_name}'. Known tools: {list(TOOL_REGISTRY.keys())}")
        return False

    # Verify tool file exists
    tool_info = TOOL_REGISTRY[tool_name]
    tool_path = Path(__file__).parent.parent / tool_info["path"]

    if not tool_path.exists():
        print(f"Error: Tool file not found: {tool_path}")
        return False

    # Verify tool can be imported and has required functions
    try:
        spec = importlib.util.spec_from_file_location(tool_name, tool_path)
        if spec is None or spec.loader is None:
            print(f"Error: Cannot load tool spec: {tool_name}")
            return False

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Check for main function or run alias
        if not hasattr(module, tool_name) and not hasattr(module, "run"):
            print(f"Error: Tool {tool_name} has no callable function (need '{tool_name}' or 'run')")
            return False

    except Exception as e:
        print(f"Error importing tool {tool_name}: {e}")
        return False

    # Registration data
    redis_key = f"tools:{tool_name}"
    registration_data = {
        "name": tool_info["name"],
        "description": tool_info["description"],
        "path": tool_info["path"],
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    if dry_run:
        print(f"Would register tool '{tool_name}':")
        print(f"  Redis key: {redis_key}")
        for key, value in registration_data.items():
            print(f"  {key}: {value}")
        return True

    # Register in Redis
    try:
        client = await get_redis_client()
        await client.hset(redis_key, mapping=registration_data)
        await client.aclose()
        print(f"Successfully registered tool '{tool_name}' in Redis")
        return True
    except Exception as e:
        print(f"Error registering tool in Redis: {e}")
        print("Make sure Redis is running and REDIS_URL is set correctly")
        return False


async def check_status(tool_name: str) -> dict | None:
    """Check registration status of a tool.

    Args:
        tool_name: Name of the tool to check

    Returns:
        Tool metadata dict or None if not registered
    """
    try:
        client = await get_redis_client()
        redis_key = f"tools:{tool_name}"
        data = await client.hgetall(redis_key)
        await client.aclose()
        return data if data else None
    except Exception as e:
        print(f"Error checking status: {e}")
        return None


async def register_all(dry_run: bool = False) -> int:
    """Register all known tools.

    Args:
        dry_run: If True, only print what would be done

    Returns:
        Number of tools successfully registered
    """
    success_count = 0
    for tool_name in TOOL_REGISTRY:
        if await register_tool(tool_name, dry_run):
            success_count += 1
    return success_count


def main():
    parser = argparse.ArgumentParser(description="Register tools in Redis")
    parser.add_argument("tool_name", nargs="?", help="Tool name to register")
    parser.add_argument("--all", action="store_true", help="Register all known tools")
    parser.add_argument("--status", action="store_true", help="Check registration status")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done")
    parser.add_argument("--list", action="store_true", help="List all known tools")

    args = parser.parse_args()

    if args.list:
        print("Known tools:")
        for name, info in TOOL_REGISTRY.items():
            print(f"  {name}: {info['description']}")
        return

    if args.all:
        count = asyncio.run(register_all(args.dry_run))
        print(f"Registered {count}/{len(TOOL_REGISTRY)} tools")
        return

    if not args.tool_name:
        parser.print_help()
        return

    if args.status:
        data = asyncio.run(check_status(args.tool_name))
        if data:
            print(f"Tool '{args.tool_name}' is registered:")
            for key, value in data.items():
                print(f"  {key}: {value}")
        else:
            print(f"Tool '{args.tool_name}' is not registered in Redis")
        return

    asyncio.run(register_tool(args.tool_name, args.dry_run))


if __name__ == "__main__":
    main()
