# Claude Code + MCP setup

This project uses **Claude Code CLI** as the executor (see `services/executor/README.md`). Claude Code gets its tools and browser automation via **MCP** (Model Context Protocol). This doc walks through installing Claude Code and configuring MCP for this repo.

## 1. Install Claude Code CLI

- **npm** (recommended):  
  `npm install -g @anthropic-ai/claude-code`
- **macOS (Homebrew):**  
  `brew install claude-code`

**API key (skip browser setup):** If you already have an Anthropic API key, set it in `.env` and Claude Code will use it — no browser or `claude setup` needed:

```bash
# In .env (from repo root)
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

Or export it in your shell: `export ANTHROPIC_API_KEY=sk-ant-...`. The executor loads `.env` before spawning the CLI, so running `python -m services.executor "..."` from repo root will pass the key.

If you prefer the interactive flow, run `claude setup` once (it may open a browser); otherwise the env var is enough.

Verify install:

```bash
claude --version
claude --help
```

## 2. MCP config in this project

MCP servers can be configured at three scopes:

| Scope    | Where it’s stored              | Use case                          |
|----------|--------------------------------|-----------------------------------|
| **local**  | `~/.claude.json` (per project) | Personal / experimental           |
| **project**| `.mcp.json` in repo root        | Shared with team (commit this)    |
| **user**  | `~/.claude.json` (global)        | Your tools across all projects    |

This repo includes a **project-scoped** `.mcp.json` so everyone gets the same MCP servers. Secrets are **not** stored in the file; we use environment variable expansion (e.g. `${BROWSERBASE_API_KEY}`).

### 2.1 Set env vars for MCP

In your `.env` (repo root), set at least the keys used by the MCP servers you enable:

- `ANTHROPIC_API_KEY` — Claude Code (skip browser setup)
- `BROWSERBASE_API_KEY`, `BROWSERBASE_PROJECT_ID` — for Browserbase MCP
- `GEMINI_API_KEY` — optional; Stagehand inside Browserbase can use this for vision

Get Browserbase credentials from [Browserbase Dashboard](https://www.browserbase.com/overview).

### 2.2 What’s in `.mcp.json`

- **browserbase** — Browser automation (navigate, click, fill forms, extract, screenshots) via [Browserbase](https://docs.browserbase.com/integrations/mcp/setup) + Stagehand. Requires `BROWSERBASE_API_KEY` and `BROWSERBASE_PROJECT_ID` in your environment (e.g. from `.env` when you run the executor).

Claude Code expands `${VAR}` and `${VAR:-default}` in `.mcp.json` when it starts MCP servers, so the file is safe to commit.

### 2.3 Use Claude Code in this repo

From the **repo root** (so Claude Code sees `.mcp.json` and your env):

```bash
# Interactive
claude

# Headless (what the executor uses)
claude -p "Open https://example.com and tell me the page title" --output-format json
```

Or run our executor (it spawns the CLI with task context):

```bash
python -m services.executor "Open https://example.com and tell me the page title"
```

## 3. Managing MCP servers

- List servers:  
  `claude mcp list`
- Details for one server:  
  `claude mcp get browserbase`
- Remove a server:  
  `claude mcp remove browserbase`

To **add** a server manually (instead of editing `.mcp.json`):

- **HTTP:**  
  `claude mcp add --transport http <name> <url>`
- **Stdio (local process):**  
  `claude mcp add --transport stdio [--scope project] [--env KEY=value] <name> -- <command> [args...]`

Example — add Browserbase at **user** scope (your machine only):

```bash
claude mcp add --transport stdio --scope user \
  --env BROWSERBASE_API_KEY="$BROWSERBASE_API_KEY" \
  --env BROWSERBASE_PROJECT_ID="$BROWSERBASE_PROJECT_ID" \
  browserbase -- npx -y @browserbasehq/mcp-server-browserbase
```

## 4. Optional: more MCP servers

- **GitHub** (code, PRs, issues):  
  `claude mcp add --transport http github https://api.githubcopilot.com/mcp/`  
  Then in Claude Code use `/mcp` to authenticate.
- **Filesystem** (read/write files):  
  Often built-in; if you use a separate MCP server, add it via `claude mcp add` or `.mcp.json` per its docs.

Add project-scoped servers either by editing `.mcp.json` (and using `${VAR}` for secrets) or by running `claude mcp add --scope project ...`.

## 5. References

- [Claude Code: Run programmatically (headless)](https://docs.anthropic.com/en/docs/claude-code/headless)
- [Claude Code: Connect to tools via MCP](https://code.claude.com/docs/en/mcp)
- [Browserbase MCP setup](https://docs.browserbase.com/integrations/mcp/setup)
