#!/bin/bash
# Launch Builder (which IS Claude Code)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SYSTEM_PROMPT=$(cat "$SCRIPT_DIR/prompts/system.txt")

cd "$REPO_ROOT"

# PRD intake with safe default when missing
PRD_FILE="$SCRIPT_DIR/requests/current_prd.yaml"
if [ -f "$PRD_FILE" ] && [ -s "$PRD_FILE" ]; then
    # PRD exists and is non-empty
    PRD_CONTENT=$(cat "$PRD_FILE")
    PRD_STATUS="PRD loaded from requests/current_prd.yaml"
else
    # Safe default when PRD is missing or empty
    PRD_CONTENT="# No PRD pending
prd:
  status: none
  message: No PRD file found in requests/current_prd.yaml
  action_required: Wait for Orchestrator or FULLSEND to provide a PRD"
    PRD_STATUS="No PRD pending - Builder is idle"
fi

claude -p "$SYSTEM_PROMPT

## PRD Status
$PRD_STATUS

## Current PRD
$PRD_CONTENT

## Existing Tools (for reference)
$(ls -la tools/*.py 2>/dev/null || echo "No tools yet")
" --allowedTools "Edit,Bash,Write,Read,Glob,Grep" \
  --dangerously-skip-permissions
