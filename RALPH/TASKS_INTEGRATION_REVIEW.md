# Tasks

Context:
- PRD: `docs/prd/PRD_INTEGRATION_REVIEW.md`
- System map: `SYSTEM_COMPONENTS.md`
- Status docs in `docs/status/`

- [x] TASK-001: Review `services/watcher/` for datetime, channels, Pydantic v2, memory bounds, and connection flags per PRD.
- [x] TASK-002: Review `services/orchestrator/` for same issues per PRD.
- [x] TASK-003: Review `services/executor/` for same issues per PRD.
- [x] TASK-004: Review `services/roundtable/` for same issues per PRD (include hardcoded weave ID + API key validation).
- [x] TASK-005: Verify channel wiring across services matches PRD reference table.
- [x] TASK-006: Create integration test `tests/integration/test_message_flow.py` per PRD.
- [x] TASK-007: Update status docs + `SYSTEM_COMPONENTS.md` per PRD.
