# Redis & RabbitMQ Schema (Fresh Start)

Assume Redis and RabbitMQ can be wiped and recreated. This doc is the single source of truth.

---

## Redis

All values are JSON unless noted. Use `decode_responses=True` and serialize with `json.dumps` / `json.loads`.

### 1. Tools (what the orchestrator can assign to agents)

| Key | Type | Value | Written by | Read by |
|-----|------|--------|------------|---------|
| `tools:available` | string (JSON) | Array of `{ "name", "description", "constraints" }` | Seed script from config file; **builder** when it adds a new tool (`append_tool_to_available`) | Orchestrator (at plan time) |

- Env override: `REDIS_TOOLS_KEY` (default `tools:available`).

- **Load in real time:** Orchestrator can GET `tools:available` on every task (or at startup). Builder appends new tools here when it ships a capability.

### 2. Skills (real-time loadable; Claude Code / Cursor)

| Key | Type | Value | Written by | Read by |
|-----|------|--------|------------|---------|
| `skills:index` | string (JSON) | Array of skill IDs: `["hubspot-sync", "airflow-dag"]` | Builder when it adds a skill | Any consumer that lists skills |
| `skill:{id}` | string (JSON) | `{ "id", "name", "description", "content", "addresses_blocked", "updated_at" }` | Builder (`register_skill` in tools_loader) | Consumers that load a skill in real time (`get_skill`, `list_skills`) |

- **`content`:** Full skill body (e.g. SKILL.md text or code).
- **`addresses_blocked`:** Optional array of `{ "task", "reason" }` this skill unblocks.
- **Real time:** Consumers GET `skills:index`, then GET `skill:{id}` for each; no restart needed.

### 3. Task state (orchestrator phase 2)

| Key | Type | Value | Written by | Read by |
|-----|------|--------|------------|---------|
| `task:{uuid}` | string (JSON) | `{ "context", "previous_steps", "next_steps", "blocked", "updated_at" }` | Orchestrator | Workers, check_redis_doable |
| `task:{uuid}:blocked` | string (JSON) | Array of `{ "task", "reason" }` | Orchestrator | Analyzer, check_redis_blocked |

- **uuid** = orchestrator task_id (e.g. from hash_service).
- One key per consumed GTM task. Workers (later) update `previous_steps` / `next_steps` when they run steps.

### 4. Campaign (user specifies topic and limits)

| Key | Type | Value | Written by | Read by |
|-----|------|--------|------------|---------|
| `campaign:active` | string (JSON) | `{ "topic", "limits": { "max_spend", "max_emails", ... }, "created_at" }` | User / API when starting a campaign | Roundtable, orchestrator, builders |

- Optional until you add campaign API; then roundtable/orchestrator read limits from here.

### 5. Approval (future: human-in-the-loop)

| Key | Type | Value | Written by | Read by |
|-----|------|--------|------------|---------|
| `approval:pending` | string (JSON) | Array of `{ "id", "type", "payload", "created_at" }` | Orchestrator or builder when something needs approval | Approval UI / consumer |
| `approval:{id}` | string (JSON) | Full request + status | Same | Same |

- Reserved for later; no code required now.

### Redis key summary

```
tools:available          → list of tools
skills:index             → list of skill ids
skill:{id}               → one skill (content, metadata)
task:{uuid}              → task state (context, steps, blocked)
task:{uuid}:blocked      → blocked list for that task
campaign:active          → current campaign topic + limits
approval:pending         → (future) items needing human approval
approval:{id}            → (future) one approval request
```

---

## RabbitMQ

All queues are durable. Message body is JSON.

### 1. Orchestrator tasks (roundtable → orchestrator)

| Queue | Payload | Published by | Consumed by |
|-------|---------|--------------|-------------|
| `fullsend.orchestrator.tasks` | `{ "task", "topic", "source", "created_at", "order" }` | Roundtable | Orchestrator daemon |

### 2. Worker steps (orchestrator → workers)

| Queue | Payload | Published by | Consumed by |
|-------|---------|--------------|-------------|
| `fullsend.worker.steps` | `{ "task_id", "task", "topic", "order", "step_index", "step", "source", "created_at" }` | Orchestrator | Executor daemon |

### 3. Worker step results (executor → dashboards / orchestrator)

| Queue | Payload | Published by | Consumed by |
|-------|---------|--------------|-------------|
| `fullsend.worker.results.worked` | `{ "task_id", "task", "topic", "order", "step_index", "step", "result", "source", "created_at" }` | Executor daemon | Dashboards, analytics |
| `fullsend.worker.results.failed` | Same + `"error_preview"` (short result snippet) | Executor daemon | Alerts, retry logic |

- Executor publishes one message per step to **worked** or **failed** depending on outcome (result looks like success vs executor error / invalid key / etc.).
- Env: `WORKER_RESULTS_WORKED_QUEUE`, `WORKER_RESULTS_FAILED_QUEUE` (defaults above).

### 4. Builder tasks (analyzer → builder consumer)

| Queue | Payload | Published by | Consumed by |
|-------|---------|--------------|-------------|
| `fullsend.builder.tasks` | See below | Analyzer | Builder consumer (you, later) |

**Builder message (enriched for Claude Code):**

```json
{
  "task": "Do this first: Build a HubSpot sync agent that ...",
  "topic": "What tools to build so blocked GTM tasks can run",
  "order": 1,
  "source": "analyzer",
  "created_at": "ISO8601",
  "format": "builder_instruction",
  "blocked_context": [
    { "task": "Program a Python script that syncs HubSpot contacts...", "reason": "No HubSpot API tool" }
  ]
}
```

- **`format`:** Always `"builder_instruction"` so the consumer knows how to present this to Claude Code.
- **`blocked_context`:** Full list of blocked tasks from this analyzer run; Claude Code knows what capability this instruction is meant to address.

### 5. Human to-do (builder → humans)

| Queue | Payload | Published by | Consumed by |
|-------|---------|--------------|-------------|
| `fullsend.human.todo` | `{ "task", "reason", "context", "source", "created_at" }` | Builder agent | Human-in-the-loop UI / ticketing |

- Builder agent publishes here when it **cannot** build a practical tool for a failure (e.g. needs API keys, legal review, or custom code it can’t generate).
- Env: `HUMAN_TODO_QUEUE` (default `fullsend.human.todo`).

### 6. Approval queue (future)

| Queue | Payload | Published by | Consumed by |
|-------|---------|--------------|-------------|
| `fullsend.approval.requests` | TBD | Orchestrator / builder | Human approval UI |

- Reserved; no implementation yet.

---

## Flow (autonomous)

1. **User** sets campaign (topic + limits) → `campaign:active` (and/or CLI arg for now).
2. **Roundtable** runs → publishes GTM tasks to `fullsend.orchestrator.tasks`.
3. **Orchestrator** consumes → reads `tools:available` → plans next_steps + blocked → publishes steps to `fullsend.worker.steps` → writes `task:{uuid}`, `task:{uuid}:blocked`.
4. **Executor daemon** consumes from `fullsend.worker.steps` → loads task + skills from Redis → runs each step (Claude Code + Browserbase) → updates Redis `task:{uuid}` → publishes outcome to `fullsend.worker.results.worked` or `fullsend.worker.results.failed`.
5. **Analyzer** runs → reads all blocked from Redis → roundtable (builder mode) → publishes to `fullsend.builder.tasks` with `blocked_context` + `format: builder_instruction`.
6. **Builder consumer** (you, later) consumes → hands enriched message to Claude Code → builder adds new tool to `tools:available` and new skill to `skills:index` + `skill:{id}`.
7. **Builder agent** (optional) consumes from `fullsend.worker.results.failed` → summarizes failures → for each: builds a practical tool (Redis) or publishes to `fullsend.human.todo` (human-in-the-loop).
8. Orchestrator (and others) read `tools:available` and `skill:{id}` in real time; no restart.

---

## Migration from current keys (fresh start)

If you had older keys, map as follows and then delete old ones:

- `orchestrator:available_tools` → `tools:available` (code now uses `REDIS_TOOLS_KEY` default `tools:available`)
- `task:*` and `task:*:blocked` → unchanged (same shape)
- New: `skills:index`, `skill:{id}` (builder adds here; loadable in real time)
