#!/usr/bin/env python3
"""Check Redis for tasks that CAN run and their implementation steps. Reads task:* (context + next_steps)."""

import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def main():
    try:
        import redis
    except ImportError:
        print("redis package not installed. pip install redis", file=sys.stderr)
        sys.exit(1)

    try:
        r = redis.from_url(REDIS_URL, decode_responses=True)
        r.ping()
    except Exception as e:
        print(f"Redis connection failed: {e}", file=sys.stderr)
        sys.exit(1)

    task_keys = [k for k in r.keys("task:*") if not k.endswith(":blocked")]

    if not task_keys:
        print("No task state keys found in Redis (task:*).")
        return

    print("--- Tasks that can run (and their steps) ---\n")

    for key in sorted(task_keys):
        try:
            raw = r.get(key)
            if not raw:
                continue
            data = json.loads(raw)
            task_id = key.replace("task:", "")
            context = data.get("context", "")
            next_steps = data.get("next_steps") or []
            blocked = data.get("blocked") or []

            if not next_steps:
                print(f"Task ID: {task_id}")
                print(f"  Context: {context[:200]}..." if len(context) > 200 else f"  Context: {context}")
                print("  Steps (doable): (none)")
                if blocked:
                    print(f"  Blocked: {len(blocked)} item(s) — run check_redis_blocked.py for details.")
                print()
                continue

            print(f"Task ID: {task_id}")
            print(f"  Context: {context[:200]}..." if len(context) > 200 else f"  Context: {context}")
            print("  Steps (doable):")
            for i, step in enumerate(next_steps, 1):
                print(f"    {i}. {step}")
            if blocked:
                print(f"  Blocked: {len(blocked)} item(s) — run check_redis_blocked.py for details.")
            print()
        except Exception as e:
            print(f"  Error reading {key}: {e}\n")


if __name__ == "__main__":
    main()
