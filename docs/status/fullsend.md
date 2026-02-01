# Status: fullsend

State: COMPLETE
Started: 2026-02-01T03:14:29-08:00
Completed: 2026-02-01T11:45:00-08:00

## Inputs
- PRD: docs/prd/PRD_FULLSEND.md
- Tasks: RALPH/TASKS_FULLSEND.md

## Outputs
- services/fullsend/run.sh (Claude Code entry point)
- services/fullsend/listener.py (Redis listener daemon) **NEW**
- services/fullsend/__init__.py, __main__.py (module support) **NEW**
- services/fullsend/prompts/system.txt
- services/fullsend/requests/current.md
- services/fullsend/experiments/SPEC_FORMAT.md
- services/fullsend/experiments/TOOL_REQUEST_FORMAT.md
- services/fullsend/experiments/examples/*.yaml (3 examples)
- services/fullsend/scripts/redis_publish.sh
- services/fullsend/scripts/REDIS_PUBLISH_GUIDE.md
- services/fullsend/ralph.sh (RALPH loop spawner)
- services/fullsend/tests/test_plan.sh

## What It Does
FULLSEND has two components:

### 1. Listener Daemon (`listener.py`)
Central coordinator for the experiment lifecycle:
- Subscribes to `fullsend:to_fullsend`, `fullsend:builder_results`, `fullsend:experiment_results`
- Writes incoming requests to `requests/current.md`
- Spawns `run.sh` (or `ralph.sh` for complex tasks)
- Handles full experiment loop:
  - When tools are built → triggers pending experiments
  - When experiments fail → routes errors appropriately:
    - `ToolNotFoundError` → auto-requests tool build
    - API key errors → escalates to user via Discord
    - Other errors → notifies orchestrator

**Run:** `uv run python -m services.fullsend.listener`

### 2. Claude Code Agent (`run.sh`)
The actual experiment designer:
1. Read request from `requests/current.md`
2. Design experiment with real templates (no placeholders)
3. Output YAML spec to `experiments/`
4. Publish to Redis: experiment, schedule, metrics spec
5. Request tools from Builder if needed
6. Spawn RALPH loops for complex multi-step tasks

## Redis Integration

**Subscribes to:**
- `fullsend:to_fullsend` - Receives experiment requests from Orchestrator
- `fullsend:builder_results` - Tool build completions from Builder
- `fullsend:experiment_results` - Execution results from Executor

**Publishes to:**
- `fullsend:experiments` - New experiment specs (Executor listens)
- `fullsend:schedules` - Schedules (Executor listens)
- `fullsend:builder_tasks` - Tool build requests (Builder listens)
- `fullsend:execute_now` - Trigger experiment execution (Executor listens)
- `fullsend:to_orchestrator` - Status updates (started, completed, failed, errors)
- `metrics_specs:{id}` - Store metrics specs for Redis Agent

**Redis Keys:**
- `pending_experiments:{tool_name}` - Set of experiment IDs waiting for a tool to be built

## Key Decisions
- Listener daemon bridges Redis pub/sub → file-based Claude Code
- HTML comment stripping for request detection
- YAML spec format with validation rules
- RALPH spawner for multi-step builds (unique work IDs)
- 10-minute default timeout for Claude Code execution
- Full loop wiring: listener handles builder/executor results to complete the cycle
- Auto-retry on missing tools: stores pending experiment, requests build, triggers on completion
- Smart error routing: API errors escalate to user, code bugs notify orchestrator

## Blockers
None
