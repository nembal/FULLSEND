# Tasks

Context:
- PRD: `docs/prd/PRD_WATCHER.md`
- System map: `SYSTEM_COMPONENTS.md`
- Discord message format: `docs/discord.md`

- [x] TASK-001: Confirm Redis channels and message formats in PRD; document any conflicts in `docs/status/watcher.md`.
- [x] TASK-002: Create `services/watcher/` skeleton with `main.py`, `config.py`, `classifier.py`, `responder.py`, `prompts/`.
- [x] TASK-003: Implement classifier prompt + JSON parsing to `ignore | answer | escalate` with priority.
- [x] TASK-004: Implement responder that reads Redis keys only (status, counts) for simple queries.
- [x] TASK-005: Implement escalation payload shape to `fullsend:to_orchestrator` with context fields.
- [x] TASK-006: Add retry logic for model calls; on failure, escalate with reason.
- [x] TASK-007: Add unit/integration tests from PRD test plan.
- [x] TASK-008: Verify PRD acceptance criteria and record checklist status.
