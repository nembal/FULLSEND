# Fullsend

An autonomous GTM agent that ships ideas continuously, builds its own tools, and gets smarter over time.

See [VISION.md](./VISION.md) for the full concept and architecture. Current plan and next steps: [PLAN.md](./PLAN.md).

## Orchestrator (Conda)

```bash
cd orchestrator

# Create env (first time): conda env create -f environment.yml
# Or use existing: conda activate weave_hacks

conda activate weave_hacks
pip install -r requirements.txt   # if not already installed
cp .env.example .env              # then add WANDB_KEY (or OPENAI_API_KEY) and REDIS_URL
python orchestrator.py
```

### LangChain agent + redis-mcp-server (MCP → localhost:6379)

Same env and LLM as above; the agent talks to **Redis at localhost:6379** via the official [redis-mcp-server](https://github.com/redis/mcp-redis) (MCP tools).

1. **Redis running** at localhost:6379: `brew services start redis` (or set `REDIS_URL` in `.env`, e.g. `redis://localhost:6379/0`).
2. **uv on PATH** (used to run redis-mcp-server): `curl -LsSf https://astral.sh/uv/install.sh | sh` then `source $HOME/.local/bin/env`. Or install redis-mcp-server with pip and set `REDIS_MCP_USE_UV=0`.
3. **Run the agent:** `python agent.py`  
   The agent uses the orchestrator LLM and **redis-mcp-server** MCP tools (strings, hashes, lists, sets, streams, JSON, etc.) to read/write Redis.
4. **Modules:** `orchestrator.py` (LLM + weave), `agent.py` (LangChain ReAct agent + langchain-mcp-adapters + redis-mcp-server). Optional: `redis_tools.py` (direct Redis LangChain tools, not used by agent when MCP is used).

**No cmake:** This repo does not use cmake. If pip asks for cmake (or fails building a dependency), install using prebuilt wheels only:  
`pip install --only-binary :all: -r requirements.txt`  
If one package still builds from source, install that package via conda or upgrade pip/setuptools and try again.

**uv without Homebrew (avoids cmake):** If `brew install uv` fails (e.g. "No available formula cmake"), install uv via the standalone script instead:  
`curl -LsSf https://astral.sh/uv/install.sh | sh`  
Then restart the terminal or run `source $HOME/.local/bin/env`; `uv` will be on your PATH.
