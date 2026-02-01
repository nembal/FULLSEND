# Fullsend System Build Plan

## Overview

Build all 10 components of the autonomous GTM agent system. Target: 1 hour with parallel agent builders.

---

## Current State

| Component | Status |
|-----------|--------|
| Discord Service | ✅ Built |
| Redis | 🔶 Needs config |
| Watcher | 🔶 To build |
| Orchestrator | 🔶 To build |
| FULLSEND | 🔶 To build |
| Builder | 🔶 To build |
| Executor | 🔶 To build |
| Redis Agent | 🔶 To build |
| Roundtable | 🔶 To build |
| Moltbook | 🔶 To integrate |

---

## Build Phases (Parallelized)

### Phase 1: Foundation (Parallel - 15 min)

| Agent | Task | Output |
|-------|------|--------|
| Agent A | Redis setup + docker-compose base | `docker-compose.yml`, Redis running |
| Agent B | Context files + schedule system | `context/`, `config/schedule.yaml` |
| Agent C | Shared utilities | `shared/redis_client.py`, `shared/claude_spawner.py` |

### Phase 2: Core Services (Parallel - 20 min)

| Agent | Task | Depends On |
|-------|------|------------|
| Agent D | Orchestrator | Phase 1 |
| Agent E | FULLSEND (Claude Code spawner) | Phase 1 |
| Agent F | Executor + schedule.yaml integration | Phase 1 |

### Phase 3: Support Services (Parallel - 15 min)

| Agent | Task | Depends On |
|-------|------|------------|
| Agent G | Watcher | Phase 1 |
| Agent H | Redis Agent | Phase 1 |
| Agent I | Builder (Claude Code spawner) | Phase 1 |

### Phase 4: Polish (Parallel - 10 min)

| Agent | Task | Depends On |
|-------|------|------------|
| Agent J | Roundtable | Phase 2 |
| Agent K | Moltbook integration | Phase 2 |
| Agent L | Docker compose finalization + integration test | All above |

---

## Key Files to Create

### 1. Schedule System
```
config/
└── schedule.yaml
```

```yaml
# config/schedule.yaml
mode: trigger  # trigger | cron | speedrun

# Trigger mode: waits for Redis/Discord events
trigger:
  channels:
    - fullsend:to_orchestrator
    - fullsend:to_fullsend
    - fullsend:builder_tasks

# Cron mode: scheduled execution
cron:
  orchestrator_wakeup: "0 9 * * *"  # Daily 9am
  experiment_check: "*/30 * * * *"  # Every 30 min

# Speedrun mode: continuous loop for demo
speedrun:
  interval_seconds: 5
  max_experiments_per_cycle: 3
  auto_approve_experiments: true

# Global
enabled: true
```

### 2. Claude Code Spawner Utility
```
shared/
└── claude_spawner.py
```

Spawns Claude Code subprocess for FULLSEND and Builder:
- Configures working directory
- Passes context via stdin or temp files
- Captures output
- Handles timeout and errors

### 3. Context Files
```
context/
├── product_context.md    # Human writes: what we're selling
├── worklist.md           # Orchestrator manages: priorities
└── learnings.md          # Orchestrator manages: insights
```

### 4. Docker Compose
```yaml
# docker-compose.yml
services:
  redis:
    image: redis:alpine
    ports: ["6379:6379"]
    volumes: [redis_data:/data]

  discord:
    build: ./services/discord
    env_file: .env
    depends_on: [redis]

  watcher:
    build: ./services/watcher
    env_file: .env
    depends_on: [redis]

  orchestrator:
    build: ./services/orchestrator
    env_file: .env
    volumes:
      - ./context:/app/context
      - ./config:/app/config
    depends_on: [redis]

  fullsend:
    build: ./services/fullsend
    env_file: .env
    volumes:
      - ./tools:/app/tools
      - ./context:/app/context
    depends_on: [redis]

  builder:
    build: ./services/builder
    env_file: .env
    volumes:
      - ./tools:/app/tools
      - ./.git:/app/.git
    depends_on: [redis]

  executor:
    build: ./services/executor
    env_file: .env
    volumes:
      - ./tools:/app/tools
      - ./config:/app/config
    depends_on: [redis]

  redis_agent:
    build: ./services/redis_agent
    env_file: .env
    depends_on: [redis]

  roundtable:
    build: ./services/roundtable
    env_file: .env
    depends_on: [redis]

volumes:
  redis_data:
```

---

## Component Specs (Summary)

### Orchestrator
- **Runtime**: Python daemon with Anthropic API (extended thinking)
- **Model**: claude-sonnet-4-20250514 with thinking
- **Listens**: `fullsend:to_orchestrator`
- **Publishes**: `fullsend:from_orchestrator`, `fullsend:to_fullsend`, `fullsend:builder_tasks`
- **Files**: Reads/writes `context/worklist.md`, `context/learnings.md`

### FULLSEND (Claude Code Spawner)
- **Runtime**: Python service that spawns Claude Code subprocess
- **Trigger**: Message on `fullsend:to_fullsend`
- **Output**: Experiment specs to Redis, tool requests to Builder
- **Key**: Has access to `tools/` directory, can run experiments directly

### Builder (Claude Code Spawner)
- **Runtime**: Python service that spawns Claude Code subprocess
- **Trigger**: PRD on `fullsend:builder_tasks`
- **Output**: New tools in `tools/`, commits to git
- **Key**: YOLO mode, commits directly to main

### Executor
- **Runtime**: Python worker pool (no LLM)
- **Trigger**: Cron OR speedrun loop based on `config/schedule.yaml`
- **Reads**: `experiments:*`, `tools:*`, `schedules:*`
- **Output**: Metrics to `fullsend:metrics`

### Watcher
- **Runtime**: Haiku-based filter
- **Listens**: `fullsend:discord_raw`
- **Output**: Filtered/escalated messages to `fullsend:to_orchestrator`

### Redis Agent
- **Runtime**: Haiku/Sonnet monitor
- **Listens**: `fullsend:metrics`
- **Output**: Alerts to `fullsend:to_orchestrator`

### Roundtable
- **Runtime**: Multi-agent orchestration
- **Trigger**: Called by Orchestrator when stuck
- **Output**: Ideas back to Orchestrator

---

## Claude Code Spawning Pattern

```python
# shared/claude_spawner.py

import subprocess
import tempfile
import os
from pathlib import Path

async def spawn_claude_code(
    prompt: str,
    working_dir: Path,
    timeout: int = 300,
    model: str = "claude-sonnet-4-20250514"
) -> str:
    """Spawn Claude Code subprocess and return output."""

    # Write prompt to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write(prompt)
        prompt_file = f.name

    try:
        result = subprocess.run(
            ["claude", "--model", model, "--print", "-f", prompt_file],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={
                **os.environ,
                "CLAUDE_AUTO_ACCEPT": "1",  # YOLO mode
            }
        )
        return result.stdout
    finally:
        Path(prompt_file).unlink()
```

---

## PRD Template for Builder Agents

Each component PRD should include:

```markdown
# PRD: {Component Name}

## Overview
- Role: {one sentence}
- Runtime: {Python daemon | Claude Code spawner | Worker pool}
- Model: {Haiku | Sonnet | Opus | None}

## File Structure
services/{name}/
├── __init__.py
├── main.py
├── config.py
└── prompts/
    └── system.txt

## Dependencies
- Redis channels: {list}
- Other services: {list}
- Config files: {list}

## Core Logic
{Pseudocode or detailed description}

## Prompts
{For AI agents: the system prompt content}

## Acceptance Criteria
- [ ] Connects to Redis
- [ ] Handles messages on {channel}
- [ ] Outputs to {channel}
- [ ] {Component-specific criteria}

## Test
{How to verify it works}
```

---

## Verification Plan

1. **Unit**: Each service starts without error
2. **Integration**: Discord message flows through Watcher → Orchestrator → FULLSEND
3. **E2E Demo**:
   - Send idea via Discord `/idea "test GitHub stargazers"`
   - Orchestrator receives and dispatches to FULLSEND
   - FULLSEND designs experiment
   - Executor runs (in speedrun mode)
   - Results appear in Discord

---

## Pre-requisites (Human Tasks)

1. [ ] Write `context/product_context.md` - what are we selling?
2. [ ] Ensure `.env` has all API keys (Anthropic, Discord, Resend, Browserbase)
3. [ ] Create Discord bot and get token
4. [ ] Set up Redis (local or Docker)

---

## Files to Modify/Create

| Path | Action |
|------|--------|
| `docker-compose.yml` | Create |
| `config/schedule.yaml` | Create |
| `context/product_context.md` | Create (human) |
| `context/worklist.md` | Create (empty template) |
| `context/learnings.md` | Create (empty template) |
| `shared/__init__.py` | Create |
| `shared/redis_client.py` | Create |
| `shared/claude_spawner.py` | Create |
| `tools/__init__.py` | Create |
| `services/watcher/` | Create (full service) |
| `services/orchestrator/` | Create (full service) |
| `services/fullsend/` | Create (full service) |
| `services/builder/` | Create (full service) |
| `services/executor/` | Create (full service) |
| `services/redis_agent/` | Create (full service) |
| `services/roundtable/` | Create (full service) |
