# Fullsend

An autonomous GTM agent that ships ideas continuously, builds its own tools, and gets smarter over time.

See [VISION.md](./VISION.md) for the full concept and architecture.

## Quick Start

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and setup
git clone <repo-url>
cd fullsend
uv sync

# Configure Discord bot
cp .env.example .env
# Edit .env with your DISCORD_TOKEN and DISCORD_GUILD_ID

# Run Discord service
uv run python -m services.discord.main
```

## Project Structure

```
fullsend/
├── services/
│   ├── discord/       # Discord bot + Web dashboard
│   ├── orchestrator/  # Main brain (coming soon)
│   ├── executor/      # Tool runner (coming soon)
│   └── context/       # Redis context management (coming soon)
├── tools/             # Agent-built tools (coming soon)
└── shared/            # Shared types (coming soon)
```

## Services

### Discord (`services/discord/`)

Communication interface - Discord bot + web dashboard that connects humans to the agent.

```bash
# Run Discord bot only
ENV=discord uv run python -m services.discord.main

# Run web dashboard only
ENV=web uv run python -m services.discord.main

# Run both
ENV=both uv run python -m services.discord.main
```

**Features:**
- Slash commands: `/status`, `/pause`, `/go`, `/idea`, `/focus`, `/learn`, `/wtf`
- Ambient listening in configured channels
- Emoji reactions on captured ideas
- Action requests with human-in-the-loop
- Real-time web dashboard at `http://localhost:8000`

## Development

```bash
# Install all dependencies
uv sync

# Add a dependency to a service
uv add <package> --package fullsend-discord

# Run tests
uv run pytest

# Lint
uv run ruff check .
```

## Requirements

- Python 3.11+
- Redis (for pub/sub between services)
- Discord bot token (create at discord.com/developers)
