#!/usr/bin/env python3
"""
Inspect Redis for tools and skills (e.g. after builder agent + register_ralph_tools).
Run from repo root: python scripts/verify_redis_tools.py
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")


def main() -> int:
    from services.orchestrator.tools_loader import (
        get_available_tools,
        list_skills,
        get_skill,
        REDIS_TOOLS_KEY,
        REDIS_SKILLS_INDEX,
    )

    print("=== Redis tools & skills ===\n")

    tools = get_available_tools()
    print(f"Tools ({REDIS_TOOLS_KEY}): {len(tools)}")
    for t in tools:
        name = t.get("name", "?")
        desc = (t.get("description") or "")[:60]
        print(f"  - {name}: {desc}...")
    print()

    skill_ids = list_skills()
    print(f"Skills ({REDIS_SKILLS_INDEX}): {len(skill_ids)}")
    for sid in skill_ids:
        skill = get_skill(sid)
        if skill:
            name = skill.get("name", sid)
            content_len = len(skill.get("content") or "")
            blocked = skill.get("addresses_blocked") or []
            print(f"  - {sid}: name={name}, content_len={content_len}, addresses_blocked={len(blocked)}")
        else:
            print(f"  - {sid}: (missing)")
    print("=== done ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
