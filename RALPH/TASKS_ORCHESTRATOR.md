# Tasks

Context:
- PRD: `docs/prd/PRD_ORCHESTRATOR.md`
- System map: `SYSTEM_COMPONENTS.md`
- Context files: `context/` (create if missing)

- [x] TASK-001: Confirm Redis channels/keys and context file paths from PRD; note any conflicts.
- [x] TASK-002: Create `services/orchestrator/` skeleton with `main.py`, `agent.py`, `context.py`, `dispatcher.py`, `config.py`, `prompts/`.
- [x] TASK-003: Implement context loader that reads `context/product_context.md`, `worklist.md`, `learnings.md` with safe fallback.
- [x] TASK-004: Implement extended-thinking model call and strict decision parsing (action, payload, priority).
- [x] TASK-005: Implement dispatcher actions: to FULLSEND, Builder, Discord, Roundtable, worklist updates, learning append, kill.
- [x] TASK-006: Implement timeouts and error handling (fallback responses).
- [x] TASK-007: Add unit/integration tests per PRD test plan.
- [x] TASK-008: Verify PRD acceptance criteria and record checklist status.
