#!/usr/bin/env python3
"""
Register tools/skills from RALPH/builder_output/*.json to Redis.
Ralph (Claude Code) creates these JSON files when completing builder-driven tasks;
this script reads them and calls append_tool_to_available + register_skill.

Run from repo root: python scripts/register_ralph_tools.py
"""

import json
import logging
import sys
from pathlib import Path

# Repo root = parent of scripts/
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

BUILDER_OUTPUT = REPO_ROOT / "RALPH" / "builder_output"


def main() -> int:
    from services.orchestrator.tools_loader import append_tool_to_available, register_skill

    if not BUILDER_OUTPUT.is_dir():
        logger.info("No RALPH/builder_output directory; nothing to register.")
        return 0

    registered: list[str] = []
    for path in sorted(BUILDER_OUTPUT.glob("*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            name = (data.get("name") or path.stem).strip()
            if not name:
                continue
            description = (data.get("description") or "").strip() or f"Tool: {name}"
            constraints = (data.get("constraints") or "").strip() or "Use when executor step failed for this kind of task."
            skill_content = (data.get("skill_content") or "").strip() or f"# {name}\n\n{description}"
            addresses_blocked = data.get("addresses_blocked")
            if not isinstance(addresses_blocked, list):
                addresses_blocked = []

            tool = {"name": name, "description": description, "constraints": constraints}
            append_tool_to_available(tool)
            register_skill(
                skill_id=name,
                name=name.replace("-", " ").title(),
                description=description,
                content=skill_content,
                addresses_blocked=addresses_blocked,
            )
            registered.append(name)
            logger.info("Registered tool/skill: %s", name)
        except Exception as e:
            logger.warning("Failed to register %s: %s", path.name, e)

    if not registered:
        logger.info("No JSON files registered.")
    else:
        logger.info("Registered %d tool(s): %s", len(registered), registered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
