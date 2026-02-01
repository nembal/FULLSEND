# Tasks

Context:
- PRD: `docs/prd/PRD_FULLSEND.md`
- System map: `SYSTEM_COMPONENTS.md`
- Redis contracts in PRD

- [x] TASK-001: Create `services/fullsend/` skeleton with `run.sh`, `prompts/system.txt`, `requests/`, `experiments/`, `status/`.
- [x] TASK-002: Implement request ingestion from `requests/current.md` (default to "No request pending").
- [x] TASK-003: Define YAML experiment spec format with full template and real examples (no placeholders).
- [x] TASK-004: Define tool request YAML format when needed; ensure PRD alignment.
- [x] TASK-005: Implement Redis publish flow for experiments, schedules, and tool requests.
- [x] TASK-006: Add RALPH loop spawn path for complex multi-step tasks.
- [x] TASK-007: Add basic test plan from PRD (sample request → spec output).
- [x] TASK-008: Verify PRD acceptance criteria and record checklist status.
