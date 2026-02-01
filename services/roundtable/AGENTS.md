# Roundtable — Agent Guide

This document gives an agent (or human) everything needed to understand, modify, and run the roundtable service.

---

## What the Roundtable Is

The **roundtable** is an **AI idea source** for the Fullsend GTM system. Three personas—**ARTIST**, **BUSINESS**, and **TECH**—take turns in a shared conversation to generate GTM ideas. They use the **same LLM** (W&B Inference, `openai/gpt-oss-120b`) with **different system prompts** so each speaks in character. Output is a **transcript** of the debate; that transcript (or a summary) can later feed the **orchestrator** (see [VISION.md](../../VISION.md)).

- **No Discord, Redis, or other services** are started when you run the roundtable; it runs standalone.
- **Redis seed** (learnings/hypotheses injected once before the roundtable) is planned but not implemented yet; the loop does not read from Redis during execution.

---

## Architecture (One LLM, Three Prompts)

- **Single LLM**: One `ChatOpenAI` instance from [llm.py](llm.py), configured for W&B Inference. Same model for all three personas.
- **Three personas**: ARTIST, BUSINESS, TECH. Each has a **system prompt** in [personas.py](personas.py). Each turn: build messages (system + topic + full transcript so far), call `llm.invoke(messages)`, append `{ "role": "artist"|"business"|"tech", "content": "..." }` to the transcript.
- **Order per round**: ARTIST → BUSINESS → TECH, repeated for `max_rounds` (default 2).
- **Summarizer agent (at the end)**: After the roundtable loop, one LLM call outputs **3–5 actionable tasks** for **AI agents** to run campaigns **autonomously**. Tasks must be agent-executable (no human hand-holding), **cost-conscious** (prefer low-cost, high-return). **Max 10–15 lines** total. Format: "Do this first: ... Do this next: ..." etc., no preamble.
- **Monitoring**: The whole session is traced with **Weave** via `@weave.op` on `run_roundtable` in [runner.py](runner.py); project: `viswanathkothe-syracuse-university/weavehacks`.

---

## File Layout

| File | Purpose |
|------|--------|
| **llm.py** | `get_llm()` — W&B Inference only. Calls `load_dotenv()` so `.env` keys (e.g. `WANDB_KEY`, `OPENAI_API_KEY`) are loaded before reading env. |
| **personas.py** | `ROLES`, `PERSONAS`, `get_persona(role)` — system prompts for ARTIST, BUSINESS, TECH. Same LLM, different prompts. |
| **runner.py** | `run_roundtable(topic, max_rounds, seed_context)` — loop: for each round, for each role, build messages, call LLM, append to transcript; then **summarizer** call: 3–5 actionable tasks (agent-executable, cost-conscious, max 10–15 lines), "Do this first/next/..." format. Returns `{"transcript": [...], "summary": "..."}`. Uses `weave.init(...)` and `@weave.op` on `run_roundtable`. |
| **__main__.py** | CLI: reads topic from argv, `ROUNDTABLE_MAX_ROUNDS` from env, calls `run_roundtable`, prints transcript. |
| **README.md** | User-facing run instructions (conda weave_hacks, `run_roundtable.sh`). |
| **AGENTS.md** | This file — for agents/humans to understand the roundtable. |

---

## Data Flow

1. **Input**: `topic` (string), optional `seed_context` (string, e.g. future Redis learnings), `max_rounds` (int).
2. **Initial message**: If `seed_context` is set, the first user message is `"Context:\n{seed_context}\n\nTopic: {topic}"`; else just `topic`.
3. **Per turn**: For role in (ARTIST, BUSINESS, TECH), messages = `[SystemMessage(persona), HumanMessage(initial), ... one HumanMessage per prior transcript entry formatted as "[ROLE] content", HumanMessage("Your turn as ROLE. Reply in character.")]`. Then `llm.invoke(messages)`; append `{"role": role, "content": response}` to transcript.
4. **Summarizer**: One LLM call: output 3–5 actionable tasks for AI agents (autonomous, cost-conscious, max 10–15 lines), format "Do this first: ... Do this next: ..." etc., no preamble. Same LLM.
5. **Output**: `{"transcript": list of {"role", "content"}, "summary": "Do this first: ... Do this next: ..." }` (3–5 tasks, ≤10–15 lines).
6. **Orchestrator queue**: If `RABBITMQ_URL` is set, the roundtable parses the summary into individual tasks and publishes each to the RabbitMQ orchestrator queue (`services/orchestrator_queue.py`). The orchestrator agent (later) consumes from that queue and runs tasks. If RabbitMQ is unavailable or not configured, the roundtable still returns transcript and summary; publish failure is logged and ignored.

---

## Environment Variables

- **Required for LLM**: `WANDB_KEY` or `OPENAI_API_KEY` (loaded from `.env` via `load_dotenv()` in llm.py).
- **Optional**: `OPENAI_API_BASE` (default `https://api.inference.wandb.ai/v1`), `OPENAI_MODEL` (default `openai/gpt-oss-120b`).
- **Roundtable**: `ROUNDTABLE_MAX_ROUNDS` (default `2`; used by __main__.py).

---

## How to Run

- **Recommended**: From repo root, `./run_roundtable.sh "Topic: your GTM idea or question"`. The script uses conda env **weave_hacks** (`conda run -n weave_hacks python -m services.roundtable ...`).
- **Manual**: `conda activate weave_hacks`, then from repo root: `python -m services.roundtable "Topic: ..."`.
- **Programmatic**: `from services.roundtable.runner import run_roundtable; result = run_roundtable("Topic: ...", max_rounds=2, seed_context=None)`; `result["transcript"]`, `result["summary"]`.

---

## Changing Personas

Edit [personas.py](personas.py): `ARTIST_PROMPT`, `BUSINESS_PROMPT`, `TECH_PROMPT`. Keep the same structure (role, lens, “Be concise. Respond in character. Build on what the others said.”) if you want consistent behavior. Do not add or remove roles without updating `ROLES` and `PERSONAS` and the runner loop.

---

## Dependencies

- Root [pyproject.toml](../../pyproject.toml): `langchain-openai`, `langchain-core`, `python-dotenv`, `weave`. The roundtable has no separate package; it uses root deps.
- Run with **weave_hacks** conda env so Weave and LangChain are available.

---

## Relation to Fullsend

- **VISION.md**: Roundtable is an “Idea Source” that feeds the Orchestrator; it is not the orchestrator or executor.
- **Redis agent** ([services/redis/redis_agent.py](../redis/redis_agent.py)): Separate service; same LLM config (W&B) but different role (GTM orchestrator with Redis MCP tools). No shared code except the same env vars for the LLM.
- **Orchestrator queue**: [services/orchestrator_queue.py](../orchestrator_queue.py) — RabbitMQ queue `fullsend.orchestrator.tasks`. Roundtable publishes each parsed task (Do this first/next/…) as a JSON message; orchestrator (later) consumes and runs. Env: `RABBITMQ_URL`, `ORCHESTRATOR_QUEUE_NAME`.
- **Future**: Optional one-time Redis seed before the roundtable (fetch learnings/hypotheses once, pass as `seed_context`); no Redis during the loop.
