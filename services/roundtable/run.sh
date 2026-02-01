#!/bin/bash
# CLI wrapper for Roundtable service
# Usage:
#   ./run.sh "How can we reach AI startup CTOs?"  # Prompt as argument
#   ./run.sh                                      # Read JSON from stdin
#   ./run.sh input.json                           # Read from JSON file

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Change to project root for proper module resolution
cd "$PROJECT_ROOT"

if [ -n "$1" ]; then
    # Check if argument is a JSON file
    if [[ "$1" == *.json ]] && [ -f "$1" ]; then
        python -m services.roundtable "$1"
    else
        # Prompt passed as argument
        echo "{\"prompt\": \"$1\"}" | python -m services.roundtable
    fi
else
    # Read from stdin
    python -m services.roundtable
fi
