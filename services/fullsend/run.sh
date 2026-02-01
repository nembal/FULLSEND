#!/bin/bash
# Launch FULLSEND (which IS Claude Code)
# FULLSEND is the creative strategist — designs experiments, defines success metrics, sets schedules.
#
# Usage: ./run.sh
#
# FULLSEND reads the experiment request from requests/current.md and outputs
# experiment specs to experiments/*.yaml

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEM_PROMPT=$(cat "$SCRIPT_DIR/prompts/system.txt")

# Read current request (or default message)
# Ingestion: reads requests/current.md, defaults to "No request pending" if missing/empty
# Strips HTML comments (format instructions) when detecting "No request pending"
REQUEST_FILE="$SCRIPT_DIR/requests/current.md"
if [[ -f "$REQUEST_FILE" ]]; then
    CURRENT_REQUEST=$(cat "$REQUEST_FILE")

    # Strip multiline HTML comments and empty lines for content detection
    CONTENT_WITHOUT_COMMENTS=$(perl -0777 -pe 's/<!--.*?-->//gs' <<< "$CURRENT_REQUEST" | tr -s '\n' | sed '/^[[:space:]]*$/d')

    # Normalize to check: remove markdown headers, whitespace
    NORMALIZED=$(echo "$CONTENT_WITHOUT_COMMENTS" | sed 's/^#.*//g' | tr -d '[:space:]')

    # If content is empty or just "Norequestpending" (normalized), treat as no request
    if [[ -z "$NORMALIZED" ]] || [[ "$NORMALIZED" == "Norequestpending" ]]; then
        CURRENT_REQUEST="No request pending"
    fi
else
    CURRENT_REQUEST="No request pending"
fi

claude -p "$SYSTEM_PROMPT

## Current Request
$CURRENT_REQUEST
" --allowedTools "Edit,Bash,Write,Read,Glob,Grep" \
  --dangerously-skip-permissions
