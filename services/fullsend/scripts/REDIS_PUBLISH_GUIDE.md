# Redis Publish Guide for FULLSEND

This guide explains how FULLSEND publishes experiments, schedules, and tool requests to Redis for coordination with other GTM services.

## Overview

FULLSEND uses Redis for:
1. **Publishing experiments** — Store specs and notify Executor
2. **Publishing metrics specs** — Tell Redis Agent what metrics to track
3. **Publishing schedules** — Set up cron triggers for experiments
4. **Requesting tools** — Ask Builder to create new tools
5. **Notifying Orchestrator** — Report status and completions
6. **Storing learnings** — Record tactical insights for future experiments

## Quick Start

### Full Experiment Publish Flow

After designing an experiment, publish it with all dependencies:

```bash
# This single command:
# 1. Stores experiment spec at experiments:{id}
# 2. Publishes to fullsend:experiments channel
# 3. Extracts and stores metrics spec at metrics_specs:{id}
# 4. Sets up schedule at schedules:{id}
# 5. Publishes to fullsend:schedules channel
# 6. Notifies orchestrator via fullsend:to_orchestrator

./scripts/redis_publish.sh publish_experiment_full experiments/exp_20240115_github_stars.yaml
```

Output:
```
=== Publishing Experiment: exp_20240115_github_stars ===

Published experiment: exp_20240115_github_stars
  - Stored at: experiments:exp_20240115_github_stars
  - Published to: fullsend:experiments

Published metrics spec for: exp_20240115_github_stars
  - Stored at: metrics_specs:exp_20240115_github_stars

Published schedule for: exp_20240115_github_stars
  - Cron: 0 9 * * MON
  - Timezone: America/Los_Angeles
  - Stored at: schedules:exp_20240115_github_stars
  - Published to: fullsend:schedules

Notified orchestrator: experiment_ready

=== Complete ===
```

## Individual Commands

### Publish Experiment Only

```bash
./scripts/redis_publish.sh publish_experiment experiments/exp_001.yaml
```

This:
- Extracts experiment ID from YAML
- Stores full spec at `experiments:{id}` with state=draft
- Publishes event to `fullsend:experiments` channel

### Publish Metrics Spec

Extract and publish the metrics section for Redis Agent to track:

```bash
./scripts/redis_publish.sh publish_metrics experiments/exp_001.yaml
```

This:
- Extracts the `metrics:` section from the experiment YAML
- Stores it at `metrics_specs:{id}` for Redis Agent to consume
- Used by Redis Agent to know what metrics to track for this experiment

Note: `publish_experiment_full` already includes this step automatically.

### Publish Schedule

```bash
./scripts/redis_publish.sh publish_schedule exp_001 "0 9 * * MON" "America/Los_Angeles"
```

Arguments:
- `exp_001` — Experiment ID
- `"0 9 * * MON"` — Cron expression (every Monday at 9am)
- `"America/Los_Angeles"` — Timezone (optional, defaults to LA)

### Request a Tool

When designing an experiment that needs a tool that doesn't exist:

```bash
./scripts/redis_publish.sh publish_tool_request experiments/tool_requests/examples/req_001.yaml
```

This notifies Builder to create the requested tool.

### Notify Orchestrator

Send status updates to Orchestrator:

```bash
# Experiment ready
./scripts/redis_publish.sh notify_orchestrator experiment_ready \
    '"experiment_id": "exp_001"' \
    '"summary": "Testing CTO outreach via GitHub"'

# Design started
./scripts/redis_publish.sh notify_orchestrator design_started \
    '"request": "GitHub stargazer campaign"'

# Design failed
./scripts/redis_publish.sh notify_orchestrator design_failed \
    '"reason": "Missing required tool"' \
    '"blocked_by": "github_stargazer_scraper"'
```

### Store Tactical Learning

Record insights for future experiments:

```bash
./scripts/redis_publish.sh store_learning "Template A got 20% response rate vs 8% for Template B" exp_001
```

### Get Available Tools

Check what tools are available before designing experiments:

```bash
./scripts/redis_publish.sh get_tools
```

Returns JSON array of tools with their states.

### Get Recent Learnings

Review past learnings for context:

```bash
./scripts/redis_publish.sh get_learnings 10
```

## Redis Data Structures

### Experiment Storage

Key: `experiments:{id}` (Hash)
```
spec        — Full YAML spec
state       — draft | ready | running | completed | failed
created_at  — ISO timestamp
updated_at  — ISO timestamp
```

### Schedule Storage

Key: `schedules:{id}` (Hash)
```
cron        — Cron expression
timezone    — Timezone string
state       — active | paused | completed
created_at  — ISO timestamp
```

### Metrics Spec Storage

Key: `metrics_specs:{id}` (Hash)
```
metrics_yaml   — Raw YAML metrics section from experiment
experiment_id  — Related experiment ID
source         — fullsend
created_at     — ISO timestamp
```

Used by Redis Agent to track metrics for experiments. Example metrics_yaml:
```yaml
  metrics:
    - name: emails_sent
      type: counter
    - name: open_rate
      type: percentage
      formula: "emails_opened / emails_sent"
      success_threshold: 0.25
```

### Tool Request Storage

Key: `tool_requests:{id}` (Hash)
```
spec         — Full YAML spec
state        — pending | in_progress | ready | failed
requested_by — fullsend
created_at   — ISO timestamp
```

### Learning Storage

Key: `learnings:tactical:{timestamp}` (Hash)
```
text          — Learning text
experiment_id — Related experiment (optional)
source        — fullsend
created_at    — ISO timestamp
```

Index: `learnings:tactical:index` (Sorted Set)
- Score: Unix timestamp
- Member: Learning key

## Channel Message Formats

### fullsend:experiments

```json
{
  "type": "experiment_created",
  "experiment_id": "exp_20240115_github_stars",
  "source": "fullsend",
  "timestamp": "2024-01-15T10:30:00Z",
  "spec_key": "experiments:exp_20240115_github_stars"
}
```

### fullsend:schedules

```json
{
  "type": "schedule_created",
  "experiment_id": "exp_20240115_github_stars",
  "schedule": "0 9 * * MON",
  "timezone": "America/Los_Angeles",
  "source": "fullsend",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### fullsend:builder_requests

```json
{
  "type": "tool_requested",
  "request_id": "req_20240115_001",
  "tool_name": "github_stargazer_scraper",
  "source": "fullsend",
  "timestamp": "2024-01-15T10:30:00Z",
  "spec_key": "tool_requests:req_20240115_001"
}
```

### fullsend:to_orchestrator

```json
{
  "type": "experiment_ready",
  "source": "fullsend",
  "timestamp": "2024-01-15T10:30:00Z",
  "experiment_id": "exp_20240115_github_stars",
  "summary": "CTOs who starred competitor repos are high-intent prospects",
  "has_schedule": true
}
```

## Environment Configuration

Set `REDIS_URL` to configure the Redis connection:

```bash
# Default
export REDIS_URL=redis://localhost:6379

# Docker
export REDIS_URL=redis://redis:6379

# Remote
export REDIS_URL=redis://my-redis-host:6379
```

## Workflow Example

Complete FULLSEND workflow after receiving an experiment request:

```bash
# 1. Design the experiment (FULLSEND creates the YAML)

# 2. Write experiment to file
cat > experiments/exp_20240115_github_stars.yaml << 'EOF'
experiment:
  id: exp_20240115_github_stars
  hypothesis: "CTOs who starred competitor repos are high-intent prospects"
  # ... full spec ...
EOF

# 3. Check if needed tools exist
./scripts/redis_publish.sh get_tools

# 4. If tool missing, request it
./scripts/redis_publish.sh publish_tool_request tool_requests/req_github_scraper.yaml

# 5. Publish the experiment
./scripts/redis_publish.sh publish_experiment_full experiments/exp_20240115_github_stars.yaml

# 6. Record any learnings
./scripts/redis_publish.sh store_learning "GitHub stargazer targeting has 3x higher intent than generic dev lists" exp_20240115_github_stars
```
