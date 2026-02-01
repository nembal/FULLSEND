# Fullsend — Final Plan

Single source of truth for what exists and what’s next.

---

## Current state (done)

- **Orchestrator** (`orchestrator/`): LLM + Weave; `orchestrator.py` entrypoint; `agent.py` = LangChain ReAct agent using **redis-mcp-server** (MCP) for Redis at `localhost:6379` via `langchain-mcp-adapters`.
- **Redis**: Used as coordination memory (learnings, hypotheses). Run locally (e.g. `brew services start redis`) or use Upstash/Redis Cloud; see `docs/local-redis.md`.
- **Docs**: `docs/local-redis.md` (run Redis without Docker), `docs/redis-mcp-cursor.md` (Redis MCP in Cursor + stdio filter for EOF/JSON errors).
- **Script**: `scripts/mcp_stdio_filter.py` — pipe before `redis-mcp-server` in Cursor MCP config to avoid empty-newline JSON errors.

---

## Optional next steps

1. **Browser agent**  
   New LangChain agent that does ad-hoc web tasks (navigate, extract, click, fill) and uses Redis for context/results.
   - **Place**: `agents/browser/` (new).
   - **Browser**: Browserbase via official **Browserbase MCP server** (`npx @browserbasehq/mcp-server-browserbase`) — no custom Playwright tools.
   - **Redis**: Same redis-mcp-server (localhost:6379); agent reads tasks/context from Redis, writes learnings/results back.
   - **LLM / monitoring**: Same as orchestrator (W&B Inference, Weave).
   - **Deliverables**: `agents/browser/browser_agent.py`, `requirements.txt`, `.env.example`; README note that Node/npx is required for the Browserbase MCP server.

2. **Restructure (optional)**  
   Move `orchestrator/` → `agents/orchestrator/` so all agents live under `agents/`. Update README and any paths.

---

## References

- **Vision & architecture**: [VISION.md](./VISION.md)
- **Run orchestrator**: [README.md](./README.md)
- **Redis (no Docker)**: [docs/local-redis.md](./docs/local-redis.md)
- **Redis MCP in Cursor**: [docs/redis-mcp-cursor.md](./docs/redis-mcp-cursor.md)
