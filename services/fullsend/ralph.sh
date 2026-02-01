#!/bin/bash
# RALPH Loop Runner for FULLSEND
# Spawns a RALPH loop for complex multi-step tasks
#
# Usage:
#   ./ralph.sh <work_dir>           Run RALPH loop in specified directory
#   ./ralph.sh spawn <goal>         Create work dir, write TASKS.md/STATUS.md, run loop
#
# FULLSEND can spawn RALPH loops for complex tasks that require multiple steps,
# such as building a custom tool, running a multi-step research process, or
# orchestrating a complex experiment setup.
#
# Example (from FULLSEND Claude Code):
#   # Option 1: Spawn with a goal (auto-generates TASKS.md)
#   ./ralph.sh spawn "Build a GitHub stargazer scraper tool"
#
#   # Option 2: Manual setup
#   mkdir -p /tmp/fullsend_build_001
#   cat > /tmp/fullsend_build_001/TASKS.md << 'EOF'
#   # Tasks
#   - [ ] TASK-001: Research GitHub API rate limits and auth
#   - [ ] TASK-002: Write the stargazer scraper tool
#   - [ ] TASK-003: Test with a small repo
#   EOF
#   ./ralph.sh /tmp/fullsend_build_001

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAX_ITERS="${RALPH_MAX_ITERS:-50}"

# === HELPER FUNCTIONS ===

log() {
    echo "[RALPH] $1"
}

get_next_task() {
    local tasks_file="$1"
    grep -E "^- \[ \] TASK-[0-9]+:" "$tasks_file" 2>/dev/null | head -1 | grep -oE "TASK-[0-9]+" || echo ""
}

get_task_counts() {
    local tasks_file="$1"
    local total=$(grep -cE "^- \[.\] TASK-[0-9]+:" "$tasks_file" 2>/dev/null || echo "0")
    local done=$(grep -cE "^- \[x\] TASK-[0-9]+:" "$tasks_file" 2>/dev/null || echo "0")
    echo "$done/$total"
}

generate_work_id() {
    # Generate unique work ID: fullsend_YYYYMMDD_HHMMSS_random
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local random=$(head -c 4 /dev/urandom | xxd -p)
    echo "fullsend_${timestamp}_${random}"
}

# === SPAWN MODE ===

spawn_ralph_loop() {
    local goal="$1"
    local work_id=$(generate_work_id)
    local work_dir="/tmp/$work_id"

    log "Creating work directory: $work_dir"
    mkdir -p "$work_dir"

    # Write STATUS.md with goal context
    cat > "$work_dir/STATUS.md" << EOF
# RALPH Status - FULLSEND Spawn

Stage: fullsend-spawn
State: IN_PROGRESS
Started: $(date -Iseconds)
Work ID: $work_id

## Goal
$goal

## Context
This RALPH loop was spawned by FULLSEND for a complex multi-step task.
Parent service: FULLSEND (services/fullsend/)

## Progress Notes
- Loop initialized by FULLSEND spawn

## Files Changed
(To be updated as tasks complete)
EOF

    log "Generating TASKS.md for goal: $goal"

    # Use Claude to generate TASKS.md from the goal
    local tasks_prompt="You are breaking down a complex goal into executable tasks for a RALPH loop.

Goal: $goal

Generate a TASKS.md file with specific, actionable tasks. Each task should be:
- Small enough to complete in one Claude Code session
- Clear about what to do and how to verify it's done
- Numbered sequentially (TASK-001, TASK-002, etc.)

Output ONLY the TASKS.md content, nothing else. Format:

# Tasks

Context:
- Goal: [the goal]
- Work dir: $work_dir

- [ ] TASK-001: [First task description]
- [ ] TASK-002: [Second task description]
- [ ] TASK-003: [Third task description]
...

Include 3-8 tasks. Be specific and actionable."

    # Generate tasks using Claude
    local tasks_content=$(claude -p "$tasks_prompt" --allowedTools "Read,Glob,Grep" 2>&1) || {
        log "ERROR: Failed to generate tasks"
        rm -rf "$work_dir"
        exit 1
    }

    # Write TASKS.md
    echo "$tasks_content" > "$work_dir/TASKS.md"

    log "Created TASKS.md with tasks"
    log "Starting RALPH loop..."

    # Run the RALPH loop
    run_ralph_loop "$work_dir"
}

# === RUN MODE ===

run_ralph_loop() {
    local work_dir="$1"
    local tasks_file="$work_dir/TASKS.md"
    local status_file="$work_dir/STATUS.md"

    if [[ ! -f "$tasks_file" ]]; then
        log "ERROR: TASKS.md not found in $work_dir"
        exit 1
    fi

    log "Starting RALPH loop in: $work_dir"
    log "Working directory: $(pwd)"

    local iter=0

    while [ $iter -lt $MAX_ITERS ]; do
        iter=$((iter + 1))

        local current_task=$(get_next_task "$tasks_file")
        local task_counts=$(get_task_counts "$tasks_file")

        # All tasks done
        if [ -z "$current_task" ]; then
            echo ""
            echo "════════════════════════════════════════════"
            echo "  ✅ ALL TASKS COMPLETE! ($task_counts)"
            echo "════════════════════════════════════════════"
            echo ""

            # Update STATUS.md with completion
            if [[ -f "$status_file" ]]; then
                sed -i '' "s/State: IN_PROGRESS/State: COMPLETE/" "$status_file" 2>/dev/null || \
                sed -i "s/State: IN_PROGRESS/State: COMPLETE/" "$status_file"
            fi

            log "Done."
            return 0
        fi

        echo ""
        echo "════════════════════════════════════════════"
        echo "  RALPH ITERATION $iter / $MAX_ITERS"
        echo "  Task: $current_task ($task_counts done)"
        echo "  Work dir: $work_dir"
        echo "════════════════════════════════════════════"
        echo ""

        # Build the prompt
        local prompt="You are completing task $current_task from $tasks_file.

Read $tasks_file to find your task.
Read $status_file for context from previous tasks (memory).

Do the task. When done:
1. Run only the checks the task explicitly asks for
2. Update $status_file with what you did (files changed, notes)
3. Mark task done: change \`- [ ] $current_task:\` to \`- [x] $current_task:\` in $tasks_file
4. Output: **TASK_DONE**"

        # Run Claude
        local output=$(claude -p "$prompt" --allowedTools Edit,Bash,Write,Read,Glob,Grep 2>&1) || true

        # Check for done signal
        if echo "$output" | grep -q "TASK_DONE"; then
            log "✅ $current_task complete"

            # Verify it's marked done
            if ! grep -qE "^- \[x\] $current_task:" "$tasks_file"; then
                log "⚠️  Task not marked done in TASKS.md - will retry"
            fi
        else
            log "⚠️  No TASK_DONE signal - will retry"
        fi

        sleep 2
    done

    echo ""
    log "⚠️ Hit max iterations ($MAX_ITERS)"
    return 1
}

# === MAIN ===

case "${1:-}" in
    spawn)
        if [[ -z "${2:-}" ]]; then
            echo "Usage: $0 spawn <goal>"
            echo "Example: $0 spawn 'Build a GitHub stargazer scraper tool'"
            exit 1
        fi
        spawn_ralph_loop "$2"
        ;;
    "")
        echo "Usage:"
        echo "  $0 <work_dir>     Run RALPH loop in specified directory"
        echo "  $0 spawn <goal>   Create work dir, generate TASKS.md, run loop"
        echo ""
        echo "Examples:"
        echo "  $0 /tmp/fullsend_build_001"
        echo "  $0 spawn 'Build a GitHub stargazer scraper tool'"
        exit 1
        ;;
    *)
        # Assume it's a work directory path
        run_ralph_loop "$1"
        ;;
esac
