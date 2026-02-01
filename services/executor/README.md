# Executor (Claude Code CLI launcher)

The executor **does not** implement its own agent loop. It spawns the **Claude Code CLI** with task context and lets Claude Code do its thing: orchestration, tools, and MCP are handled by Claude Code.

## Prerequisites

1. **Install Claude Code** (Agent SDK CLI), e.g.:
   - `npm install -g @anthropic-ai/claude-code` (or `brew install claude-code` on macOS).
   - **API key:** Set `ANTHROPIC_API_KEY` in `.env` (or export it) to skip browser / `claude setup`. See [Claude Code + MCP setup](../../docs/claude_code_mcp_setup.md).
2. **Configure MCP in Claude Code** (e.g. Browserbase for browser automation):
   - This repo includes a project-scoped `.mcp.json` with Browserbase. Set `BROWSERBASE_API_KEY` and `BROWSERBASE_PROJECT_ID` in `.env` (see [Claude Code + MCP setup](../../docs/claude_code_mcp_setup.md)).
   - Or run `claude mcp add` to add servers manually; MCP and API keys are managed by Claude Code.

## Env (optional)

- `CLAUDE_CLI_PATH` — Path to `claude` binary (default: `claude` in PATH).
- `EXECUTOR_ALLOWED_TOOLS` — Comma-separated tools to auto-approve (e.g. `Read,Edit,Bash`). Omit to use Claude Code defaults.
- `EXECUTOR_SYSTEM_PROMPT` — Extra system prompt (e.g. “You are running GTM tasks.”).
- `RABBITMQ_URL` — For daemon: RabbitMQ connection URL (default: `amqp://localhost:5672/`).
- `STEPS_QUEUE_NAME` — For daemon: queue to consume (default: `fullsend.worker.steps`).
- `WORKER_RESULTS_WORKED_QUEUE` — For daemon: queue to publish when a step worked (default: `fullsend.worker.results.worked`).
- `WORKER_RESULTS_FAILED_QUEUE` — For daemon: queue to publish when a step didn't work (default: `fullsend.worker.results.failed`).
- `REDIS_URL` — For daemon: Redis URL for task state and skills (default: `redis://localhost:6379/0`).

## Run

**Single task** (from repo root):

```bash
python -m services.executor "Open https://example.com and tell me the page title"
```

**Daemon** (consume from worker steps queue; load task + skills from Redis; run each step with Claude Code + Browserbase; update task state in Redis):

```bash
python -m services.executor --daemon
```

Optional: `--max-messages N` to process at most N steps then exit; `--time-limit N` to run for at most N seconds. The daemon consumes from `fullsend.worker.steps` (orchestrator publishes there), loads task context from Redis (`task:{uuid}`) and **all skills** from Redis (`skills:index` → `skill:{id}`), runs the executor for each step, then updates Redis (`previous_steps` / `next_steps`).

With context and steps (e.g. when called from orchestrator):

```python
from services.executor.runner import run, build_prompt

result = run(
    "Do the steps below.",
    context="GTM: improve landing page conversion",
    steps=["Open the landing page", "Fill the signup form with test data", "Submit and note the result"],
)
```

If the Claude Code CLI is not installed or not in PATH, the executor returns a clear error asking you to install it and configure MCP.

## Legacy

`tools.py` and `browserbase_stagehand.py` are the old custom agent loop (Anthropic API + Stagehand). They are unused by the launcher; we rely on Claude Code + MCP instead.
