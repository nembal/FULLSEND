# Current Task: TASK-015

**Progress**: 14/15 tasks complete

You are working on ONE task. Complete it, mark it done, then output TASK_DONE.

---

## Your Task

- [ ] TASK-015: Add svix Package Dependency

**File**: `package.json`

**Goal**: Ensure svix package is installed for webhook verification

**Changes**:
1. Check if `svix` is in dependencies
2. If not, run `pnpm add svix`
3. Verify types are available

**Test**: `pnpm install` succeeds, no type errors

---

---

## Project Context

This task is part of the Admin Dashboard v2 project. See full PRD at `docs/PRD_ADMIN_DASHBOARD_V2.md`.

**Overall goal**: Redesign admin dashboard with unified activity table showing user journey (signup → verification → endorsement → completion + email status).

**Key constraints**:
- Follow existing code patterns in `components/admin/`
- Use Shadcn UI components from `components/ui/`
- Support dark mode (CSS variables from `globals.css`)
- TypeScript strict mode — no `any` types
- Use `@/*` import aliases

**Related files you may need**:
- Full task list: `RALPH/TASKS.md`
- PRD: `docs/PRD_ADMIN_DASHBOARD_V2.md`
- Admin components: `components/admin/`
- UI components: `components/ui/`
- API routes: `app/api/admin/`

---

## When Complete

1. Ensure your changes work with existing code
2. Run `pnpm lint` and fix any errors
3. In `RALPH/TASKS.md`, change `- [ ] TASK-015:` to `- [x] TASK-015:`
4. Output exactly: **TASK_DONE**
