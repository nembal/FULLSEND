# Redis MCP Server in Cursor

The Redis MCP server can fail with:

```text
Invalid JSON: EOF while parsing a value at line 2 column 0
input_value='\n'
```

That happens when the client (Cursor) sends empty newlines; the server tries to parse them as JSON and errors. Use the stdio filter so the server never sees empty lines.

## 1. Make sure Redis is running

Local Redis (Homebrew):

```bash
brew services start redis
# or: redis-server
```

Test: `redis-cli ping` → `PONG`.

## 2. Run the server with the filter (no uv)

From the **project root** (GTM_agent_auto_mode_on), with `redis-mcp-server` installed (e.g. `pip install redis-mcp-server` in base or your env):

```bash
python scripts/mcp_stdio_filter.py | redis-mcp-server --url redis://localhost:6379/0
```

If you use **uv** and have it on your PATH (`source $HOME/.local/bin/env`):

```bash
python scripts/mcp_stdio_filter.py | uv run redis-mcp-server --url redis://localhost:6379/0
```

## 3. Cursor MCP config

In Cursor: **Settings → MCP** (or `.cursor/mcp.json`), add the Redis server with the filtered command. Example `mcp.json`:

```json
{
  "mcpServers": {
    "redis": {
      "command": "sh",
      "args": [
        "-c",
        "python scripts/mcp_stdio_filter.py | redis-mcp-server --url redis://localhost:6379/0"
      ],
      "cwd": "/Users/sindhukothe/VISH/WEAVEhacks/GTM_agent_auto_mode_on"
    }
  }
}
```

Use your real project path for `cwd`. If you use uv:

```json
"args": ["-c", "python scripts/mcp_stdio_filter.py | uv run redis-mcp-server --url redis://localhost:6379/0"]
```

## 4. If you don’t need the Redis MCP server

You can use Redis from Python (orchestrator) with the `redis` package and `REDIS_URL` in `.env`; no MCP server required.
