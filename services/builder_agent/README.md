# Builder agent

Consumes **everything that didn't work** (from `fullsend.worker.results.failed`), summarizes with an LLM, classifies each failure as **build_tool** or **human_todo**, then:

- **build_tool**: Uses the **Ralph loop** to build: appends tasks to `RALPH/TASKS.md`, runs `RALPH/ralph.sh` (Claude Code does each task), then runs `scripts/register_ralph_tools.py` to register any `RALPH/builder_output/*.json` to Redis (`tools:available` + `skill:{id}`).
- **human_todo**: Publishes a message to the **human-to-do queue** (`fullsend.human.todo`) for things the builder can't automate (e.g. API keys, legal review, unclear requirements).

**Not integrated into `run_demo.py` yet** — run standalone to test.

## Prerequisites

- **RabbitMQ**: `fullsend.worker.results.failed` (executor publishes here when a step fails); `fullsend.human.todo` (builder publishes human tasks here).
- **Redis**: Tools/skills are written by Ralph (Claude Code) into `RALPH/builder_output/*.json`, then `scripts/register_ralph_tools.py` loads them into Redis.
- **LLM**: Same as orchestrator (`OPENAI_API_KEY` or `ORCHESTRATOR_LLM_API_KEY`, or `WANDB_KEY`).
- **Claude Code CLI**: For Ralph loop (`RALPH/ralph.sh`); `ANTHROPIC_API_KEY` in env.

## Env (optional)

- `RABBITMQ_URL` — default `amqp://localhost:5672/`
- `WORKER_RESULTS_FAILED_QUEUE` — default `fullsend.worker.results.failed`
- `HUMAN_TODO_QUEUE` — default `fullsend.human.todo`
- `REDIS_URL` — for tools/skills (used by `register_ralph_tools.py`)

## Run

From repo root. Use your project conda env (e.g. `weave_hacks`) so dependencies (pika, langchain, etc.) are available:

```bash
# Seed the failed queue with 3 test messages (so the builder has something to consume)
conda run -n weave_hacks python -m services.builder_agent --seed-queue

# Process all failed messages (Ralph loop builds tools; may take several minutes)
conda run -n weave_hacks python -m services.builder_agent

# Process at most 5
conda run -n weave_hacks python -m services.builder_agent --max 5
```

Output: number of tools built (and slugs), number of human-todo items published, and a short list of human tasks.

## Flow

1. Drain `fullsend.worker.results.failed` (up to `--max`).
2. LLM: summarize failures and for each item decide **build_tool** (with tool_name, description, constraint) or **human_todo** (human_task, human_reason).
3. For each **build_tool**: append a task to `RALPH/TASKS.md` (create `RALPH/builder_output/tool_<slug>.json`, run `scripts/register_ralph_tools.py`). Run `RALPH/ralph.sh` so Claude Code completes each task. Run `scripts/register_ralph_tools.py` to register any JSONs Ralph created to Redis.
4. For each **human_todo**: publish to `fullsend.human.todo` with `task`, `reason`, `context`, `source`, `created_at`.
5. Log and print counts.

## Human-to-do queue

Payload published to `fullsend.human.todo`:

```json
{
  "task": "What the human should do",
  "reason": "Why the builder couldn't do it",
  "context": "Step/error context",
  "source": "builder_agent",
  "created_at": "ISO8601"
}
```

Consumers (e.g. human-in-the-loop UI or ticketing) can subscribe to this queue; no integration in this repo yet.
