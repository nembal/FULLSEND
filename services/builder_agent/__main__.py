"""
Run builder agent standalone (not integrated into run_demo yet).

  python -m services.builder_agent              # process all failed messages (Ralph loop builds)
  python -m services.builder_agent --max 5      # process at most 5
  python -m services.builder_agent --seed-queue # add 3 test messages to failed queue first
"""

import argparse
import logging
import sys

from .runner import run_builder_agent, seed_failed_queue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Builder agent: consume executor failures, summarize, Ralph loop builds tools, send rest to human-to-do queue."
    )
    parser.add_argument("--max", type=int, default=None, help="Process at most N failed messages")
    parser.add_argument("--seed-queue", action="store_true", help="Add 3 test messages to fullsend.worker.results.failed")
    parser.add_argument("--seed-count", type=int, default=3, help="Number of test messages when using --seed-queue (default 3)")
    args = parser.parse_args()

    if args.seed_queue:
        n = seed_failed_queue(count=args.seed_count)
        print(f"Seeded {n} test message(s) to failed queue. Run without --seed-queue to process them.")
        return 0

    built, human_todo, slugs, items = run_builder_agent(max_messages=args.max)
    print(f"Built {built} tool(s): {slugs}")
    print(f"Human todo: {human_todo} item(s)")
    for h in items:
        print(f"  - {h.get('task', '')[:60]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
