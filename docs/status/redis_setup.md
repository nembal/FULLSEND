# Status: redis setup

State: COMPLETE
Started: 2026-02-01
Completed: 2026-02-01

## Purpose
Document the local Redis setup required for Fullsend services and the demo dashboard.

## Prerequisites
- macOS with Homebrew installed
- Python 3.11+

## Install Redis (Homebrew)
```bash
brew install redis
```

## Start Redis (Background Service)
```bash
brew services start redis
```

## Verify Redis is Running
```bash
redis-cli ping
```
Expected: `PONG`

## Stop Redis (Optional)
```bash
brew services stop redis
```

## Environment Variables
Set in `.env` (repo root):
```
REDIS_URL=redis://localhost:6379
```

## Demo Dashboard Notes
The Discord web UI reads Redis for demo summary data.
- Run the web UI: `ENV=web uv run python -m services.discord.main`
- Open: `http://localhost:8000`

Optional log stream for demo timelines:
```
DEMO_LOGS_ENABLED=1
```
Logs are written to `demo/dashboard/logs.txt`.

## Troubleshooting
- `redis-cli: command not found`: Redis not installed; run `brew install redis`.
- `Redis not running`: run `brew services start redis`.
- `Connection refused`: confirm Redis is on `localhost:6379` and `REDIS_URL` matches.
