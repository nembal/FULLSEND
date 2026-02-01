#!/usr/bin/env python3
"""Check Redis for tasks that aren't working (blocked). Reads task:* and task:*:blocked."""

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

    # Keys: task:* (full state with blocked) and task:*:blocked (blocked only)
    task_keys = [k for k in r.keys("task:*") if not k.endswith(":blocked")]
    blocked_keys = r.keys("task:*:blocked")

    if not task_keys and not blocked_keys:
        print("No task state or blocked keys found in Redis (task:* or task:*:blocked).")
        return

    print("--- Blocked tasks (tasks that couldn't be carried out) ---\n")

    # Prefer task:*:blocked for explicit blocked lists
    for key in sorted(blocked_keys):
        try:
            raw = r.get(key)
            if not raw:
                continue
            blocked = json.loads(raw)
            task_id = key.replace("task:", "").replace(":blocked", "")
            print(f"Task ID: {task_id}")
            print(f"Key: {key}")
            for i, b in enumerate(blocked if isinstance(blocked, list) else [blocked], 1):
                task_desc = b.get("task", b) if isinstance(b, dict) else str(b)
                reason = b.get("reason", "") if isinstance(b, dict) else ""
                print(f"  {i}. {task_desc}")
                if reason:
                    print(f"     Reason: {reason}")
            print()
        except Exception as e:
            print(f"  Error reading {key}: {e}\n")

    # Also show blocked from full task state (task:* without :blocked)
    for key in sorted(task_keys):
        try:
            raw = r.get(key)
            if not raw:
                continue
            data = json.loads(raw)
            blocked = data.get("blocked") or []
            if not blocked:
                continue
            task_id = key.replace("task:", "")
            if any(task_id in k for k in blocked_keys):
                continue  # already printed from :blocked key
            print(f"Task ID: {task_id}")
            print(f"Key: {key}")
            for i, b in enumerate(blocked, 1):
                task_desc = b.get("task", b) if isinstance(b, dict) else str(b)
                reason = b.get("reason", "") if isinstance(b, dict) else ""
                print(f"  {i}. {task_desc}")
                if reason:
                    print(f"     Reason: {reason}")
            print()
        except Exception as e:
            print(f"  Error reading {key}: {e}\n")

    # Summary: full task state keys (context, next_steps) for reference
    if task_keys:
        print("--- Task state keys (task:uuid) ---")
        for key in sorted(task_keys)[:20]:
            print(f"  {key}")
        if len(task_keys) > 20:
            print(f"  ... and {len(task_keys) - 20} more")


if __name__ == "__main__":
    main()
