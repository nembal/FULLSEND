#!/bin/bash
set -e

# === CONFIG ===
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STATUS_DIR="$REPO_ROOT/docs/status"
STATUS_TEMPLATE="$STATUS_DIR/STATUS_TEMPLATE.md"
MAX_ITERS="${RALPH_MAX_ITERS:-50}"

# Default task sequence (can be overridden by args)
DEFAULT_TASKS=(
  "$REPO_ROOT/RALPH/TASKS_WATCHER.md"
  "$REPO_ROOT/RALPH/TASKS_ORCHESTRATOR.md"
  "$REPO_ROOT/RALPH/TASKS_FULLSEND.md"
  "$REPO_ROOT/RALPH/TASKS_EXECUTOR.md"
  "$REPO_ROOT/RALPH/TASKS_REDIS_AGENT.md"
  "$REPO_ROOT/RALPH/TASKS_BUILDER.md"
  "$REPO_ROOT/RALPH/TASKS_ROUNDTABLE.md"
  "$REPO_ROOT/RALPH/TASKS_BROWSERBASE_TOOL.md"
)

cd "$REPO_ROOT"

echo "🤖 RALPH2 starting..."
echo "   Repo: $REPO_ROOT"
echo "   Status dir: $STATUS_DIR"
echo ""

# === HELPERS ===

get_next_task() {
  local tasks_file="$1"
  grep -E "^- \[ \] TASK-[0-9]+:" "$tasks_file" 2>/dev/null | head -1 | grep -oE "TASK-[0-9]+" || echo ""
}

get_task_counts() {
  local tasks_file="$1"
  local total
  local done
  total=$(grep -cE "^- \[.\] TASK-[0-9]+:" "$tasks_file" 2>/dev/null || echo "0")
  done=$(grep -cE "^- \[x\] TASK-[0-9]+:" "$tasks_file" 2>/dev/null || echo "0")
  echo "$done/$total"
}

stage_name_from_tasks_file() {
  local file_name
  file_name="$(basename "$1")"
  file_name="${file_name#TASKS_}"
  file_name="${file_name%.md}"
  echo "$file_name" | tr '[:upper:]' '[:lower:]'
}

init_status_file() {
  local status_file="$1"
  local stage_name="$2"
  local tasks_file="$3"

  if [ -f "$status_file" ]; then
    return 0
  fi

  if [ -f "$STATUS_TEMPLATE" ]; then
    cp "$STATUS_TEMPLATE" "$status_file"
  else
    cat > "$status_file" << 'EOF'
# RALPH Status

Stage:
State: IN_PROGRESS
Started:
Completed:

Inputs:
- PRD:
- Tasks file:
- Prior status:

Outputs:
- Artifacts:
- Decisions:
- Open questions:

Progress Notes:
- 

Files Changed:
- 

Completion Marker:
- STATE: COMPLETE
EOF
  fi

  {
    echo ""
    echo "Stage: $stage_name"
    echo "Started: $(date -Iseconds)"
    echo "Tasks file: $tasks_file"
  } >> "$status_file"
}

is_stage_complete() {
  local status_file="$1"
  if [ ! -f "$status_file" ]; then
    return 1
  fi
  if grep -q "STATE: COMPLETE" "$status_file"; then
    return 0
  fi
  return 1
}

run_stage() {
  local tasks_file="$1"
  local stage_name="$2"
  local status_file="$3"
  local iter=0

  if [ ! -f "$tasks_file" ]; then
    echo "⚠️  Tasks file not found: $tasks_file"
    return 1
  fi

  init_status_file "$status_file" "$stage_name" "$tasks_file"

  echo ""
  echo "════════════════════════════════════════════"
  echo "  Stage: $stage_name"
  echo "  Tasks: $tasks_file"
  echo "  Status: $status_file"
  echo "════════════════════════════════════════════"
  echo ""

  while [ $iter -lt $MAX_ITERS ]; do
    iter=$((iter + 1))

    local current_task
    local task_counts
    current_task="$(get_next_task "$tasks_file")"
    task_counts="$(get_task_counts "$tasks_file")"

    if [ -z "$current_task" ]; then
      echo ""
      echo "✅ Stage complete: $stage_name ($task_counts)"
      echo "STATE: COMPLETE" >> "$status_file"
      echo "Completed: $(date -Iseconds)" >> "$status_file"
      return 0
    fi

    echo ""
    echo "════════════════════════════════════════════"
    echo "  RALPH2 ITERATION $iter / $MAX_ITERS"
    echo "  Task: $current_task ($task_counts done)"
    echo "════════════════════════════════════════════"
    echo ""

    local prompt
    prompt="$(cat <<EOF
You are completing task $current_task from $tasks_file.

Read $tasks_file to find your task.
Read $status_file for context from previous tasks (memory).

Do the task. When done:
1. Run only the checks the task explicitly asks for
2. Update $status_file with what you did (files changed, notes)
3. Mark task done: change \`- [ ] $current_task:\` to \`- [x] $current_task:\` in $tasks_file
4. Output: **TASK_DONE**
EOF
)"

    local output
    output="$(claude -p "$prompt" --allowedTools Edit,Bash,Write,Read,Glob,Grep 2>&1)" || true

    if echo "$output" | grep -q "TASK_DONE"; then
      echo "✅ $current_task complete"

      if ! grep -qE "^- \[x\] $current_task:" "$tasks_file"; then
        echo "⚠️  Task not marked done in tasks file - will retry"
      fi
    else
      echo "⚠️  No TASK_DONE signal - will retry"
    fi

    sleep 2
  done

  echo "⚠️  Stage hit max iterations ($MAX_ITERS): $stage_name"
  return 1
}

# === MAIN ===

TASKS_LIST=()
if [ "$#" -gt 0 ]; then
  for arg in "$@"; do
    TASKS_LIST+=("$arg")
  done
else
  TASKS_LIST=("${DEFAULT_TASKS[@]}")
fi

for tasks_file in "${TASKS_LIST[@]}"; do
  stage_name="$(stage_name_from_tasks_file "$tasks_file")"
  status_file="$STATUS_DIR/${stage_name}.md"

  if is_stage_complete "$status_file"; then
    echo "⏭️  Skipping completed stage: $stage_name"
    continue
  fi

  run_stage "$tasks_file" "$stage_name" "$status_file"
done

echo ""
echo "✅ RALPH2 finished all stages."
