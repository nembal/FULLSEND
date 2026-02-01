"""
CLI:
  python -m services.executor "Open example.com and tell me the page title"
  python -m services.executor --daemon   # consume from fullsend.worker.steps, load skills from Redis
"""

import argparse
import sys

from .runner import run
from .worker import run_executor_daemon


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Executor: run a single task (Claude Code + Browserbase) or daemon (consume steps queue)."
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Consume from worker steps queue; load task + skills from Redis and run each step.",
    )
    parser.add_argument(
        "--max-messages",
        type=int,
        default=None,
        help="Process at most N step messages then exit (daemon mode).",
    )
    parser.add_argument(
        "--time-limit",
        type=int,
        default=None,
        help="Run for at most N seconds then exit (daemon mode).",
    )
    parser.add_argument(
        "task",
        nargs="*",
        help='Single task prompt (e.g. "Open https://example.com and tell me the page title"). Ignored if --daemon.',
    )
    args = parser.parse_args()

    if args.daemon:
        run_executor_daemon(
            max_messages=args.max_messages,
            time_limit_seconds=args.time_limit,
        )
        return 0

    task = " ".join(args.task).strip() if args.task else ""
    if not task:
        print("Usage: python -m services.executor \"<task>\"", file=sys.stderr)
        print("   or: python -m services.executor --daemon", file=sys.stderr)
        print("Example: python -m services.executor \"Open https://example.com and tell me the page title\"", file=sys.stderr)
        return 1
    result = run(task)
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
