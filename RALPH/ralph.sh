#!/bin/bash
set -e

# === CONFIG ===
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASKS_FILE="$SCRIPT_DIR/TASKS.md"
STATUS_FILE="$SCRIPT_DIR/STATUS.md"
MAX_ITERS=50
ITER=0

# Change to repo root
cd "$SCRIPT_DIR/.."

echo "🤖 RALPH starting..."
echo "   Working dir: $(pwd)"
echo ""

# === HELPERS ===

get_next_task() {
  grep -E "^- \[ \] TASK-[0-9]+:" "$TASKS_FILE" 2>/dev/null | head -1 | grep -oE "TASK-[0-9]+" || echo ""
}

get_task_counts() {
  local total=$(grep -cE "^- \[.\] TASK-[0-9]+:" "$TASKS_FILE" 2>/dev/null || echo "0")
  local done=$(grep -cE "^- \[x\] TASK-[0-9]+:" "$TASKS_FILE" 2>/dev/null || echo "0")
  echo "$done/$total"
}

# === MAIN LOOP ===

while [ $ITER -lt $MAX_ITERS ]; do
  ITER=$((ITER + 1))

  CURRENT_TASK=$(get_next_task)
  TASK_COUNTS=$(get_task_counts)

  # All tasks done
  if [ -z "$CURRENT_TASK" ]; then
    echo ""
    echo "════════════════════════════════════════════"
    echo "  ✅ ALL TASKS COMPLETE! ($TASK_COUNTS)"
    echo "════════════════════════════════════════════"
    echo ""
    echo "✅ Done."
    exit 0
  fi

  echo ""
  echo "════════════════════════════════════════════"
  echo "  RALPH ITERATION $ITER / $MAX_ITERS"
  echo "  Task: $CURRENT_TASK ($TASK_COUNTS done)"
  echo "════════════════════════════════════════════"
  echo ""

  # Build the prompt - simple and direct
  PROMPT="You are completing task $CURRENT_TASK from RALPH/TASKS.md.

Read RALPH/TASKS.md to find your task.
Read RALPH/STATUS.md for context from previous tasks (memory).

Do the task. When done:
1. Run only the checks the task explicitly asks for
2. Update RALPH/STATUS.md with what you did (files changed, notes)
3. Mark task done: change \`- [ ] $CURRENT_TASK:\` to \`- [x] $CURRENT_TASK:\` in RALPH/TASKS.md
4. Output: **TASK_DONE**"

  # Run Claude
  OUTPUT=$(claude -p "$PROMPT" --allowedTools Edit,Bash,Write,Read,Glob,Grep 2>&1) || true

  # Check for done signal
  if echo "$OUTPUT" | grep -q "TASK_DONE"; then
    echo "✅ $CURRENT_TASK complete"

    # Verify it's marked done
    if ! grep -qE "^- \[x\] $CURRENT_TASK:" "$TASKS_FILE"; then
      echo "⚠️  Task not marked done in TASKS.md - will retry"
    fi
  else
    echo "⚠️  No TASK_DONE signal - will retry"
  fi

  sleep 2
done

echo ""
echo "⚠️ Hit max iterations ($MAX_ITERS)"
exit 1
