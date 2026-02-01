# PRD: Integration Review & Final Wiring

## Context

The Fullsend GTM agent system has 6 core services built:
- **Discord** - Human interface (bot + web dashboard)
- **Watcher** - Message classifier (Gemini Flash)
- **Orchestrator** - Strategic decision maker (Claude Opus 4)
- **Executor** - Experiment runner (cron/trigger based)
- **Redis Agent** - Metrics monitor (Gemini Flash)
- **Roundtable** - Multi-agent ideation

All services have passing unit tests (266+), but unit tests **mock Redis** and don't verify actual channel wiring between services.

## Problem Statement

A code review of Discord and Redis Agent services found critical issues:

### Issues Found & Fixed (Discord + Redis Agent)

| Issue | Severity | Status |
|-------|----------|--------|
| `web_adapter.py` used `_connected` instead of `is_connected` | 🔴 Critical | ✅ Fixed |
| Discord channels misaligned with Watcher/Orchestrator | 🔴 Critical | ✅ Fixed |
| `datetime.utcnow()` deprecated (Python 3.12+) | 🟡 Medium | ✅ Fixed |
| Memory leaks in Discord (unbounded sets/dicts) | 🟡 Medium | ✅ Fixed |
| Redis Agent used Pydantic v1 `class Config` pattern | 🟡 Medium | ✅ Fixed |
| Redis Agent had module-level settings instantiation | 🟡 Medium | ✅ Fixed |

### Services NOT Yet Reviewed

| Service | Unit Tests | Code Reviewed? |
|---------|------------|----------------|
| Watcher | 70 pass | ❌ No |
| Orchestrator | 104 pass | ❌ No |
| Executor | 64 pass | ❌ No |
| Roundtable | 24 pass | ❌ No |

These services likely have similar issues (datetime deprecation, potential bugs, etc.)

## Corrected Channel Wiring

After the fix, the message flow is:

```
┌──────────┐   fullsend:discord_raw   ┌─────────┐
│ Discord  │ ───────────────────────► │ Watcher │
└──────────┘                          └────┬────┘
     ▲                                     │
     │                            ┌────────┴────────┐
     │                            ▼                 ▼
     │                     [simple answer]    [escalate]
     │                            │                 │
     │   fullsend:from_orchestrator                 │
     │◄───────────────────────────┘                 │
     │                                              ▼
     │                                    fullsend:to_orchestrator
     │                                              │
     │   fullsend:from_orchestrator      ┌─────────▼─────────┐
     └◄──────────────────────────────────│   Orchestrator    │
                                         └─────────┬─────────┘
                                                   │
                          ┌────────────────────────┼────────────────────────┐
                          ▼                        ▼                        ▼
               fullsend:to_fullsend     fullsend:builder_tasks    fullsend:from_orchestrator
                          │                        │                        │
                          ▼                        ▼                        ▼
                     [FULLSEND]               [Builder]               [Discord]
```

### Channel Reference

| Channel | Publisher(s) | Subscriber(s) |
|---------|--------------|---------------|
| `fullsend:discord_raw` | Discord | Watcher |
| `fullsend:to_orchestrator` | Watcher, Redis Agent | Orchestrator |
| `fullsend:from_orchestrator` | Orchestrator, Watcher | Discord |
| `fullsend:metrics` | Executor | Redis Agent |
| `fullsend:execute_now` | Orchestrator | Executor |
| `fullsend:schedules` | FULLSEND | Executor |
| `fullsend:to_fullsend` | Orchestrator | FULLSEND |
| `fullsend:builder_tasks` | Orchestrator | Builder |
| `fullsend:experiment_results` | Executor | Orchestrator |

## Tasks

### TASK-001: Code Review Watcher Service

Review `services/watcher/` for:
- [ ] `datetime.utcnow()` → `datetime.now(UTC)`
- [ ] Verify channel names match the reference table above
- [ ] Check for any `_connected` vs `is_connected` type bugs
- [ ] Check Pydantic patterns (should use v2 `model_config`)
- [ ] Check for memory leaks (unbounded collections)

Files to review:
- `services/watcher/config.py`
- `services/watcher/classifier.py`
- `services/watcher/responder.py`
- `services/watcher/escalator.py`
- `services/watcher/main.py`
- `services/watcher/retry.py`

### TASK-002: Code Review Orchestrator Service

Review `services/orchestrator/` for same issues.

Files to review:
- `services/orchestrator/config.py`
- `services/orchestrator/agent.py`
- `services/orchestrator/context.py`
- `services/orchestrator/dispatcher.py`
- `services/orchestrator/main.py`

### TASK-003: Code Review Executor Service

Review `services/executor/` for same issues.

Files to review:
- `services/executor/config.py`
- `services/executor/loader.py`
- `services/executor/runner.py`
- `services/executor/scheduler.py`
- `services/executor/metrics.py`
- `services/executor/main.py`

### TASK-004: Code Review Roundtable Service

Review `services/roundtable/` for same issues.

Files to review:
- `services/roundtable/runner.py`
- `services/roundtable/llm.py`
- `services/roundtable/personas.py`
- `services/roundtable/__main__.py`

Additional concerns:
- Hardcoded weave project ID in `runner.py:9`
- Missing API key validation in `llm.py`

### TASK-005: Verify Cross-Service Channel Wiring

Verify each service uses the correct channel names from the reference table:

| Service | Should Publish To | Should Subscribe To |
|---------|-------------------|---------------------|
| Discord | `fullsend:discord_raw` | `fullsend:from_orchestrator` |
| Watcher | `fullsend:to_orchestrator`, `fullsend:from_orchestrator` | `fullsend:discord_raw` |
| Orchestrator | `fullsend:from_orchestrator`, `fullsend:to_fullsend`, `fullsend:builder_tasks` | `fullsend:to_orchestrator` |
| Executor | `fullsend:metrics`, `fullsend:experiment_results` | `fullsend:execute_now`, `fullsend:schedules` |
| Redis Agent | `fullsend:to_orchestrator` | `fullsend:metrics` |

### TASK-006: Integration Test Script

Create a script that:
1. Starts Redis
2. Simulates a Discord message → `fullsend:discord_raw`
3. Verifies Watcher receives it
4. Verifies escalation reaches Orchestrator via `fullsend:to_orchestrator`
5. Verifies response comes back via `fullsend:from_orchestrator`

Location: `tests/integration/test_message_flow.py`

### TASK-007: Update Documentation

Update status files to reflect review completion:
- `docs/status/watcher.md`
- `docs/status/orchestrator.md`
- `docs/status/executor.md`
- `docs/status/roundtable.md`
- `SYSTEM_COMPONENTS.md` (status table)

## Acceptance Criteria

1. All `datetime.utcnow()` calls replaced with `datetime.now(UTC)` across all services
2. All channel names verified to match the reference table
3. No Pydantic v1 patterns (`class Config`) remaining
4. No potential memory leaks (all collections bounded or cleaned)
5. Integration test passes: Discord → Watcher → Orchestrator → Discord round-trip
6. All status docs updated

## Files Already Fixed (Reference)

These files were fixed in the previous session - use as reference for patterns:

### Discord Service (Fixed)
- `services/discord/core/bus.py` - Channel constants with aliases
- `services/discord/core/messages.py` - `datetime.now(UTC)` pattern
- `services/discord/adapters/web_adapter.py` - `is_connected` fix
- `services/discord/adapters/discord_adapter.py` - Memory limits

### Redis Agent Service (Fixed)
- `services/redis_agent/config.py` - Pydantic v2 `model_config` pattern
- `services/redis_agent/monitor.py` - `datetime.now(UTC)`, lazy settings
- `services/redis_agent/alerts.py` - `datetime.now(UTC)`, lazy settings
- `services/redis_agent/analyzer.py` - `datetime.now(UTC)`, lazy settings
- `services/redis_agent/main.py` - `get_settings()` function call

### Orchestrator Service (Partially Fixed)
- `services/orchestrator/context.py` - `datetime.now(UTC)` ✅
- `services/orchestrator/dispatcher.py` - `datetime.now(UTC)` ✅

### Executor Service (Partially Fixed)
- `services/executor/runner.py` - `datetime.now(UTC)` ✅
- `services/executor/main.py` - `datetime.now(UTC)` ✅

## Priority

**High** - The system will not work end-to-end without correct channel wiring. Unit tests pass but integration will fail if channels are misaligned.

## Estimated Scope

- TASK-001 to TASK-004: ~30 min each (code review + fixes)
- TASK-005: ~15 min (grep + verify)
- TASK-006: ~45 min (write integration test)
- TASK-007: ~15 min (update docs)

Total: ~3-4 hours
