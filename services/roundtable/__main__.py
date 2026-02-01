"""Run roundtable from CLI.

Usage:
    # JSON from stdin
    echo '{"prompt": "How can we reach AI CTOs?"}' | python -m services.roundtable

    # JSON file argument
    python -m services.roundtable input.json

    # Legacy: plain text argument (backward compatible)
    python -m services.roundtable "Topic: your GTM idea"
"""

import json
import os
import sys

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    from .runner import run_roundtable

    input_data = None

    # Check for file argument
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        # If it's a file path ending in .json, read it
        if arg.endswith(".json") and os.path.isfile(arg):
            with open(arg) as f:
                input_data = json.load(f)
        else:
            # Legacy: treat as plain text prompt
            topic = " ".join(sys.argv[1:]).strip()
            input_data = {"prompt": topic}
    else:
        # Read from stdin
        if not sys.stdin.isatty():
            stdin_content = sys.stdin.read().strip()
            if stdin_content:
                try:
                    input_data = json.loads(stdin_content)
                except json.JSONDecodeError:
                    # If not JSON, treat as plain text prompt
                    input_data = {"prompt": stdin_content}

    if not input_data or not input_data.get("prompt"):
        print("Usage:", file=sys.stderr)
        print("  echo '{\"prompt\": \"...\"}' | python -m services.roundtable", file=sys.stderr)
        print("  python -m services.roundtable input.json", file=sys.stderr)
        print("  python -m services.roundtable \"Topic: your GTM idea\"", file=sys.stderr)
        sys.exit(1)

    # Extract PRD input fields
    prompt = input_data["prompt"]
    context = input_data.get("context", "")
    learnings = input_data.get("learnings", [])
    max_rounds = input_data.get("max_rounds", int(os.getenv("ROUNDTABLE_MAX_ROUNDS", "3")))

    result = run_roundtable(
        prompt=prompt,
        context=context,
        learnings=learnings,
        max_rounds=max_rounds,
    )

    # Output as JSON (PRD format)
    print(json.dumps(result, indent=2))
