# Tasks

Context:
- PRD: `docs/prd/PRD_REDIS_AGENT.md`
- System map: `SYSTEM_COMPONENTS.md`
- Existing impl: `services/redis/redis_agent.py`

- [x] TASK-001: Review existing `services/redis/redis_agent.py` vs PRD behaviors and list gaps.
- [x] TASK-002: Decide location strategy (expand existing vs move to `services/redis_agent/`).
- [x] TASK-003: Implement metrics stream subscription + aggregation keys from PRD.
- [x] TASK-004: Implement threshold evaluation and alert publishing to Orchestrator with cooldown.
- [x] TASK-005: Implement periodic summaries using Gemini 2.0 Flash.
- [x] TASK-006: Add test plan checks from PRD.
- [x] TASK-007: Verify PRD acceptance criteria and record checklist status.
