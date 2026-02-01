# Tasks

Context:
- PRD: `docs/prd/PRD_BUILDER.md`
- System map: `SYSTEM_COMPONENTS.md`
- Tool contract in PRD

- [x] TASK-001: Create `services/builder/` skeleton with `run.sh`, `prompts/system.txt`, `requests/`, `templates/`, `status/`.
- [x] TASK-002: Implement PRD intake from `requests/current_prd.yaml` with safe default when missing.
- [x] TASK-003: Implement tool generation contract (function name, `run` alias, dict return, error handling).
- [x] TASK-004: Implement smoke test execution and error handling for failures.
- [x] TASK-005: Implement git add/commit flow (YOLO mode) + Redis tool registration.
- [x] TASK-006: Add RALPH loop spawn path for complex multi-file tools.
- [x] TASK-007: Add basic test plan from PRD (simple tool + complex tool).
- [x] TASK-008: Verify PRD acceptance criteria and record checklist status.
