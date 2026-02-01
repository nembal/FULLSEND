# Discord Service

This service is the communication edge of Fullsend. It provides two adapters:

- **Discord adapter**: a Discord bot that captures ideas, handles slash commands, and posts status updates.
- **Web adapter**: a lightweight web dashboard for real-time status and human-in-the-loop actions.

Together they act as the **bi-directional I/O** layer described in `VISION.md`, bridging humans and the orchestrator/executor loop.

## How It Works

1. **Startup**
   - `services/discord/main.py` loads settings from `.env`.
   - Connects to Redis (if available).
   - Starts Discord, Web, or both adapters based on `ENV`.

2. **Message Flow**
   - The adapters register handlers with a shared `MessageRouter`.
   - The router subscribes to Redis and dispatches messages to all adapters.
   - Messages from humans are published to Redis for the orchestrator to consume.

3. **Offline Mode**
   - If Redis is unavailable, adapters still run but publishing/receiving is disabled.

## Relationship To `VISION.md`

In the full system architecture, Discord is the primary **idea source** and **status/reporting channel**:

- **Input**: captures ideas, commands, and feedback from humans.
- **Output**: posts status updates, progress, and results back to Discord.
- **Bridge**: sends human messages to the orchestrator via Redis, and receives agent updates back.

This matches the VISION loop: humans propose ideas → orchestrator assigns tasks → executor returns results → Discord reports learnings.

## Relationship To `README.md`

The README lists this service as the first runnable module and the main entry point for local development:

- **Quick start** uses `uv run python services/discord/main.py`
- **Modes**:
  - `ENV=discord` runs the bot only
  - `ENV=web` runs the dashboard only
  - `ENV=both` runs both adapters

## Key Files

- `services/discord/main.py` — entry point and adapter orchestration
- `services/discord/config.py` — env config and validation
- `services/discord/core/router.py` — Redis subscription + message dispatch
- `services/discord/adapters/discord_adapter.py` — Discord bot integration
- `services/discord/adapters/web_adapter.py` — FastAPI dashboard

## Configuration

Required env vars (from `.env.example`):

- `DISCORD_TOKEN`
- `DISCORD_GUILD_ID`

Optional:

- `LISTENING_CHANNELS` (default: `ideas,gtm,brainstorm`)
- `STATUS_CHANNEL` (default: `fullsend-status`)
- `IDEA_REACT_EMOJI` (default: `🎯`)
- `REDIS_URL` (default: `redis://localhost:6379`)
- `ENV` (`discord` | `web` | `both`, default: `both`)
- `WEB_PORT` (default: `8000`)

## Run Locally

```bash
cp .env.example .env
uv run python -m services.discord.main
```
