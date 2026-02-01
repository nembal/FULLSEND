# RALPH Tasks

## Discord Communication Service - Build from PRD

- [x] TASK-001: Set up project structure
  - Create `services/discord/` folder structure per PRD
  - Create `pyproject.toml` with dependencies: discord.py, fastapi, redis, pydantic, uvicorn, python-dotenv
  - Create `.env.example` with all config vars from PRD
  - Create empty `__init__.py` files

- [x] TASK-002: Create config module
  - Create `services/discord/config.py`
  - Use Pydantic Settings to load from env
  - Include: DISCORD_TOKEN, DISCORD_GUILD_ID, LISTENING_CHANNELS, STATUS_CHANNEL, REDIS_URL, ENV, WEB_PORT
  - Add validation for required fields

- [x] TASK-003: Create message models
  - Create `services/discord/core/messages.py`
  - Define AgentMessage (type, payload, timestamp, priority)
  - Define ActionRequest (id, description, action_type, details, assignee, deadline)
  - Define HumanMessage (type, payload, source, user_id, timestamp)
  - Define IdeaSubmission (content, source_channel, submitted_by, context)
  - Use Pydantic BaseModel for all

- [x] TASK-004: Create Redis bus wrapper
  - Create `services/discord/core/bus.py`
  - Implement async Redis pub/sub connection
  - Methods: connect(), disconnect(), publish(channel, message), subscribe(channel, callback)
  - Handle connection errors gracefully
  - Use channels: `fullsend:to_agent`, `fullsend:from_agent`

- [x] TASK-005: Create basic Discord bot
  - Create `services/discord/adapters/discord_adapter.py`
  - Use discord.py Bot with intents (messages, guilds, reactions)
  - Implement on_ready event logging
  - Load config from config.py
  - Bot should connect and stay online

- [x] TASK-006: Add core slash commands
  - Add to discord_adapter.py
  - `/status` - returns "Agent is running..." (placeholder)
  - `/pause` - sets paused state, confirms
  - `/go` - resumes agent, confirms
  - Use discord.py slash command decorators

- [x] TASK-007: Add /idea command
  - Add `/idea <text>` slash command
  - Creates IdeaSubmission from input
  - Publishes to Redis bus
  - Responds with confirmation + emoji

- [x] TASK-008: Add channel listening
  - Implement on_message event handler
  - Only process messages from LISTENING_CHANNELS
  - Ignore bot messages
  - Extract message content as potential idea
  - Log captured ideas (don't publish yet, just detect)

- [x] TASK-009: Add emoji reactions
  - When idea detected in listening channel, react with target emoji
  - Use configurable emoji (default: target dart)
  - Don't send text responses in listening channels
  - Track reacted messages to avoid duplicates

- [x] TASK-010: Add action request handling
  - Listen for action_request messages from Redis
  - Post formatted action request to status channel
  - Add reaction buttons (checkmark, x)
  - on_reaction_add: detect completion, publish action_complete to Redis

- [x] TASK-011: Create main entry point
  - Create `services/discord/main.py`
  - Load config, check ENV mode
  - If discord/both: start Discord bot
  - If web/both: start FastAPI (placeholder for now)
  - Handle graceful shutdown

- [x] TASK-012: Create FastAPI web adapter
  - Create `services/discord/adapters/web_adapter.py`
  - Endpoints: GET /, GET /api/status, GET /api/feed, POST /api/command
  - Basic JSON responses (no templates yet)
  - Include CORS middleware

- [x] TASK-013: Add WebSocket support
  - Add /ws endpoint for real-time updates
  - Subscribe to Redis and forward messages to connected clients
  - Handle client connect/disconnect
  - Broadcast to all connected clients

- [x] TASK-014: Create dashboard template
  - Create `services/discord/templates/dashboard.html`
  - Simple HTML with status bar, live feed, controls
  - JavaScript WebSocket client
  - Basic CSS styling

- [x] TASK-015: Wire up Redis to both adapters
  - Connect message router to Redis bus
  - Discord adapter subscribes to from_agent channel
  - Web adapter subscribes to from_agent channel
  - Both publish to to_agent channel
  - Test round-trip message flow

- [x] TASK-016: Add proactive status posting
  - When status_update received from Redis, post to STATUS_CHANNEL
  - Format nicely with timestamp
  - Handle learning_share, win_alert message types
  - Rate limit posts (max 1 per 5 seconds)

- [x] TASK-017: Integration test script
  - Create `services/discord/test_integration.py`
  - Publish mock messages to Redis
  - Verify Discord bot responds correctly
  - Verify web dashboard receives updates
  - Document manual test steps in comments


## Builder-driven tasks (from executor failures)

- [x] TASK-018: Add tool **hubspotcontactcreator**: A wrapper that authenticates with HubSpot and creates or updates contacts via the HubSpot REST API.
  - Constraint: Requires a HubSpot API key (or OAuth token) with contacts write scope.
  - From executor failure: step "Call HubSpot API to create a contact with email test@example.com", error "No HubSpot API tool available"
  - Create RALPH/builder_output/tool_hubspotcontactcreator.json with keys: name, description, constraints, skill_content (markdown string), addresses_blocked (list of {task, reason}).
  - Run from repo root: python scripts/register_ralph_tools.py
  - Update RALPH/STATUS.md with what you did. Mark task done in TASKS.md. Output **TASK_DONE**

- [ ] TASK-019: Add tool **pythonscriptrunner**: Executes short Python scripts with network access and returns stdout as JSON.
  - Constraint: Limited to scripts under 200 lines and execution time under 30 seconds.
  - From executor failure: step "Run a Python script to fetch a page, parse HTML, and return headings and links as JSON", error "No Python script runner tool; step requires a small script"
  - Create RALPH/builder_output/tool_pythonscriptrunner.json with keys: name, description, constraints, skill_content (markdown string), addresses_blocked (list of {task, reason}).
  - Run from repo root: python scripts/register_ralph_tools.py
  - Update RALPH/STATUS.md with what you did. Mark task done in TASKS.md. Output **TASK_DONE**

- [ ] TASK-020: Add tool **genericwebscraper**: Provides a configurable scraper that extracts repeated item blocks using CSS selectors.
  - Constraint: Requires user to supply CSS selectors; respects robots.txt and rate limits.
  - From executor failure: step "Scrape the product list from a given URL and return title, price, and link for each item", error "Scraper tool not available; need a reusable scraper for list pages"
  - Create RALPH/builder_output/tool_genericwebscraper.json with keys: name, description, constraints, skill_content (markdown string), addresses_blocked (list of {task, reason}).
  - Run from repo root: python scripts/register_ralph_tools.py
  - Update RALPH/STATUS.md with what you did. Mark task done in TASKS.md. Output **TASK_DONE**

- [ ] TASK-021: Add tool **browserbasescreenshotextractor**: Wraps Browserbase API to load a page, capture a screenshot, and run a DOM query for the main heading.
  - Constraint: Requires valid Browserbase API key and supports only one navigation per call.
  - From executor failure: step "Open URL in Browserbase, take a screenshot, extract the main h1 text, and return it", error "Browserbase session failed or navigate + extract tool not configured"
  - Create RALPH/builder_output/tool_browserbasescreenshotextractor.json with keys: name, description, constraints, skill_content (markdown string), addresses_blocked (list of {task, reason}).
  - Run from repo root: python scripts/register_ralph_tools.py
  - Update RALPH/STATUS.md with what you did. Mark task done in TASKS.md. Output **TASK_DONE**

- [ ] TASK-022: Add tool **pythonscriptrunner**: Executes short Python scripts with network access and returns the script's stdout as text.
  - Constraint: Only allows scripts up to 200 lines and limits execution time to 30 seconds.
  - From executor failure: step "Run a Python script to fetch a page, parse HTML, and return headings and links as JSON", error "No Python script runner tool"
  - Create RALPH/builder_output/tool_pythonscriptrunner.json with keys: name, description, constraints, skill_content (markdown string), addresses_blocked (list of {task, reason}).
  - Run from repo root: python scripts/register_ralph_tools.py
  - Update RALPH/STATUS.md with what you did. Mark task done in TASKS.md. Output **TASK_DONE**

