# PRD: Orchestrator

## Overview

**Role:** The strategic manager — maintains context, prioritizes work, dispatches tasks to FULLSEND and Builder. The brain that decides WHAT to work on (not HOW).

**Runtime:** Python daemon with Anthropic API (extended thinking)
**Model:** Claude Opus 4 with extended thinking (maximum reasoning power)
**Container:** `fullsend-orchestrator`

---

## Model Choice: Maximum Thinking Power

The Orchestrator is the strategic brain. It needs the best reasoning available.

### Primary: Claude Opus 4 with Extended Thinking
```python
response = await anthropic.messages.create(
    model="claude-opus-4-20250514",
    max_tokens=16000,
    thinking={
        "type": "enabled",
        "budget_tokens": 10000  # Let it think DEEPLY
    },
    messages=[{"role": "user", "content": prompt}]
)
```

### Alternative: Gemini 2.0 Pro (Thinking)
If you want to use Gemini for cost savings:
```python
import google.generativeai as genai

model = genai.GenerativeModel("gemini-2.0-pro-exp")

response = model.generate_content(
    prompt,
    generation_config=genai.GenerationConfig(
        temperature=0.7,
        max_output_tokens=8000,
    )
)
```

### Why Heavy Thinking?
- Strategic decisions have high leverage
- Wrong prioritization wastes resources
- Context is complex (experiments + learnings + metrics)
- Extended thinking = better reasoning chains
- This is where "intelligence" matters most

---

## Personality

Thoughtful. Strategic. Patient. Takes time to understand before acting. Doesn't rush. Doesn't write code. Thinks deeply, then dispatches.

---

## What It Does

1. **Maintains context** via `worklist.md` and `learnings.md` files
2. **Receives escalations** from Watcher and alerts from Redis Agent
3. **Prioritizes** incoming ideas and requests
4. **Dispatches work** to FULLSEND (experiments) and Builder (tools)
5. **Decides** when to scale up, pause, or kill experiments
6. **Reports** important updates back to Discord
7. **Initiates Roundtable** when stuck or exploring new directions
8. **Writes strategic learnings** ("event targeting works", "avoid CFOs")

## What It Does NOT Do

- Write code
- Run experiments directly
- Make snap decisions
- Design experiment specs (that's FULLSEND's job)

---

## File Structure

```
services/orchestrator/
├── __init__.py
├── main.py           # Entry point (daemon loop)
├── config.py         # Pydantic settings
├── agent.py          # Core agent logic with thinking
├── context.py        # Reads/writes worklist.md, learnings.md
├── dispatcher.py     # Sends tasks to FULLSEND, Builder
└── prompts/
    ├── system.txt    # Main system prompt
    ├── dispatch.txt  # Task dispatch decisions
    └── learn.txt     # Learning extraction
```

---

## Dependencies

### Redis Channels
- **Subscribes to:** `fullsend:to_orchestrator`
- **Publishes to:**
  - `fullsend:from_orchestrator` (responses to Discord)
  - `fullsend:to_fullsend` (experiment requests)
  - `fullsend:builder_tasks` (tool PRDs)

### Redis Keys (Read)
- `experiments:*` — Active experiment states
- `tools:*` — Available tools registry
- `learnings:tactical:*` — FULLSEND's tactical learnings
- `metrics_aggregated:*` — Experiment performance

### Context Files
- `context/product_context.md` — What we're selling (human-written)
- `context/worklist.md` — Current priorities (Orchestrator-managed)
- `context/learnings.md` — Strategic insights (Orchestrator-managed)

### Python Packages
```
anthropic
redis
pydantic
pydantic-settings
aiofiles
```

### Environment Variables
```
ANTHROPIC_API_KEY=...
REDIS_URL=redis://redis:6379
ORCHESTRATOR_MODEL=claude-opus-4-20250514
ORCHESTRATOR_THINKING_BUDGET=10000
CONTEXT_PATH=/app/context
```

---

## Core Logic

### Main Loop (main.py)

```python
async def main():
    redis = Redis.from_url(REDIS_URL)
    pubsub = redis.pubsub()
    await pubsub.subscribe("fullsend:to_orchestrator")

    # Load initial context
    context = await load_context()

    async for message in pubsub.listen():
        if message["type"] == "message":
            data = json.loads(message["data"])
            await process_with_thinking(data, context)

            # Reload context after each decision (it may have changed)
            context = await load_context()
```

### Agent Logic with Extended Thinking (agent.py)

```python
async def process_with_thinking(msg: dict, context: Context) -> None:
    """Use extended thinking to make strategic decisions."""

    # Build the full context for the model
    prompt = build_prompt(msg, context)

    # Call with extended thinking enabled
    response = await anthropic.messages.create(
        model=ORCHESTRATOR_MODEL,
        max_tokens=16000,
        thinking={
            "type": "enabled",
            "budget_tokens": 10000  # Let it think deeply
        },
        messages=[
            {"role": "user", "content": prompt}
        ],
        system=load_prompt("system.txt")
    )

    # Parse the decision from response
    decision = parse_decision(response)

    # Execute the decision
    await execute_decision(decision, msg, context)

async def execute_decision(decision: Decision, msg: dict, context: Context):
    """Execute whatever the Orchestrator decided."""

    if decision.action == "dispatch_to_fullsend":
        await publish("fullsend:to_fullsend", {
            "type": "experiment_request",
            "idea": decision.payload,
            "context": decision.context_for_fullsend,
            "priority": decision.priority
        })

    elif decision.action == "dispatch_to_builder":
        await publish("fullsend:builder_tasks", {
            "type": "tool_prd",
            "prd": decision.payload,
            "requested_by": "orchestrator"
        })

    elif decision.action == "respond_to_discord":
        await publish("fullsend:from_orchestrator", {
            "type": "orchestrator_response",
            "channel_id": msg.get("channel_id"),
            "content": decision.payload
        })

    elif decision.action == "update_worklist":
        await update_worklist(decision.payload)

    elif decision.action == "record_learning":
        await append_learning(decision.payload)

    elif decision.action == "kill_experiment":
        await redis.hset(f"experiments:{decision.experiment_id}", "state", "archived")

    elif decision.action == "initiate_roundtable":
        await trigger_roundtable(decision.payload)
```

### Context Management (context.py)

```python
@dataclass
class Context:
    product: str           # From product_context.md
    worklist: str          # From worklist.md
    learnings: str         # From learnings.md
    active_experiments: list[dict]
    available_tools: list[str]
    recent_metrics: dict

async def load_context() -> Context:
    """Load all context needed for decision making."""

    # Read markdown files
    product = await read_file("context/product_context.md")
    worklist = await read_file("context/worklist.md")
    learnings = await read_file("context/learnings.md")

    # Read from Redis
    experiments = await get_active_experiments()
    tools = await get_available_tools()
    metrics = await get_recent_metrics()

    return Context(
        product=product,
        worklist=worklist,
        learnings=learnings,
        active_experiments=experiments,
        available_tools=tools,
        recent_metrics=metrics
    )

async def update_worklist(new_content: str):
    """Update worklist.md with new priorities."""
    await write_file("context/worklist.md", new_content)

async def append_learning(learning: str):
    """Append a new learning to learnings.md."""
    current = await read_file("context/learnings.md")
    timestamp = datetime.now().isoformat()
    updated = current + f"\n\n## {timestamp}\n{learning}"
    await write_file("context/learnings.md", updated)
```

---

## Prompts

### prompts/system.txt

```
You are the Orchestrator of the Fullsend autonomous GTM system.

## Your Role
You are the strategic manager. You decide WHAT to work on, not HOW to do it.
You maintain context, prioritize work, and dispatch tasks to specialists.

## Your Context
Product: {{product_context}}

Current Worklist:
{{worklist}}

Strategic Learnings:
{{learnings}}

Active Experiments:
{{experiments_summary}}

Available Tools:
{{tools_list}}

Recent Metrics:
{{metrics_summary}}

## Your Capabilities

1. **Dispatch to FULLSEND** — When you have an idea worth testing
   - Send the idea + relevant context
   - FULLSEND will design the experiment spec

2. **Dispatch to Builder** — When you need a new tool
   - Write a PRD (name, purpose, inputs, outputs)
   - Builder will create it

3. **Respond to Discord** — When you need to communicate with humans
   - Status updates, questions, reports

4. **Update Worklist** — When priorities change
   - Add new items, reprioritize, mark complete

5. **Record Learning** — When you learn something strategic
   - "Event targeting works better than cold outreach"
   - "CTOs respond, CFOs don't"

6. **Kill Experiment** — When something is clearly failing
   - Archive it, record why

7. **Initiate Roundtable** — When you're stuck or need fresh ideas
   - Spawn multi-agent debate
   - Provide context and question

## Decision Framework

When you receive a message, think through:

1. **What is this?** — Idea, report, question, alert?
2. **Is it important?** — Does it need action now?
3. **What do we already know?** — Check learnings for relevant context
4. **What should happen?** — Dispatch, respond, learn, or ignore?
5. **What's the priority?** — Where does this fit in the worklist?

## Your Personality
- Thoughtful, strategic, patient
- Take time to understand before acting
- Don't rush into experiments without thinking
- Be willing to say "not now" to ideas
- Always record learnings when things succeed or fail

## Output Format

After thinking, output your decision as:

```json
{
  "action": "dispatch_to_fullsend" | "dispatch_to_builder" | "respond_to_discord" | "update_worklist" | "record_learning" | "kill_experiment" | "initiate_roundtable" | "no_action",
  "reasoning": "Brief explanation of why",
  "payload": { ... },  // Action-specific data
  "priority": "low" | "medium" | "high" | "urgent"
}
```
```

### prompts/dispatch.txt

```
You're dispatching an idea to FULLSEND for experiment design.

## The Idea
{{idea}}

## Context to Include
- Relevant learnings: {{relevant_learnings}}
- Similar past experiments: {{similar_experiments}}
- Available tools: {{tools}}
- Constraints: {{constraints}}

Write a natural language message to FULLSEND explaining:
1. What we want to test
2. Why we think it might work (based on learnings)
3. Any tools already available
4. Any constraints or preferences

Keep it conversational. FULLSEND is an LLM, not a rigid API.
```

---

## Message Types Handled

### From Watcher (Escalations)
```json
{
  "type": "escalation",
  "source": "watcher",
  "priority": "high",
  "reason": "New GTM idea from user",
  "original_message": {
    "username": "jake",
    "content": "What if we scraped GitHub stargazers?"
  }
}
```

### From Redis Agent (Alerts)
```json
{
  "type": "metric_alert",
  "source": "redis_agent",
  "experiment_id": "exp_123",
  "alert_type": "threshold_crossed",
  "metric": "response_rate",
  "value": 0.02,
  "threshold": 0.05,
  "recommendation": "Consider killing this experiment"
}
```

### From FULLSEND (Experiment Designed)
```json
{
  "type": "experiment_ready",
  "source": "fullsend",
  "experiment_id": "exp_456",
  "summary": "GitHub stargazer cold email campaign",
  "needs_tool": false,
  "scheduled_for": "2024-01-16T09:00:00Z"
}
```

### From Builder (Tool Complete)
```json
{
  "type": "tool_complete",
  "source": "builder",
  "tool_name": "github_stargazer_scraper",
  "status": "active",
  "location": "tools/github_stargazer_scraper.py"
}
```

---

## Worklist.md Format

```markdown
# Fullsend Worklist

## Active (In Progress)
- [ ] **GitHub stargazer campaign** - FULLSEND designing, exp_123
- [ ] **LinkedIn enrichment tool** - Builder working on it

## Ready (Prioritized Queue)
1. Test YC founder outreach (high priority, Jake's idea)
2. Try conference attendee scraping (medium priority)
3. A/B test email subject lines (low priority, optimization)

## Blocked
- Event scraping - need browserbase credits

## Completed This Week
- [x] Initial cold email campaign - 12% response rate
- [x] Resend integration - tool working
```

---

## Learnings.md Format

```markdown
# Strategic Learnings

## 2024-01-15
**Event-based targeting outperforms cold lists**
- GitHub stargazer campaign: 15% response rate
- Generic cold email: 2% response rate
- Hypothesis: People at events are in "discovery mode"

## 2024-01-14
**CTOs respond, CFOs ignore**
- 50 emails to CTOs: 8 responses
- 50 emails to CFOs: 0 responses
- Action: Focus on technical buyers

## 2024-01-13
**Tuesday 9am PST is optimal send time**
- Tested Mon-Fri, various times
- Tuesday 9am: 20% open rate
- Friday 4pm: 5% open rate
```

---

## Acceptance Criteria

- [ ] Connects to Redis on startup
- [ ] Subscribes to `fullsend:to_orchestrator`
- [ ] Loads context from markdown files and Redis
- [ ] Uses extended thinking for decisions
- [ ] Dispatches experiment requests to FULLSEND
- [ ] Dispatches tool PRDs to Builder
- [ ] Sends responses back to Discord
- [ ] Updates worklist.md when priorities change
- [ ] Appends to learnings.md when insights emerge
- [ ] Can kill failing experiments
- [ ] Can initiate Roundtable sessions
- [ ] Handles all message types (escalations, alerts, completions)
- [ ] Logs decisions with reasoning

---

## Test Plan

### Unit Tests
```bash
# Test context loading
python -m services.orchestrator.context --test

# Test decision parsing
echo '{"action": "dispatch_to_fullsend", ...}' | python -m services.orchestrator.agent --parse
```

### Integration Test
```bash
# Start orchestrator
python -m services.orchestrator.main &

# Send test escalation
redis-cli PUBLISH fullsend:to_orchestrator '{
  "type": "escalation",
  "source": "watcher",
  "original_message": {"content": "Scrape HN Who is Hiring posts"}
}'

# Check for dispatch to FULLSEND
redis-cli SUBSCRIBE fullsend:to_fullsend
# Should see experiment_request within 30 seconds

# Check worklist was updated
cat context/worklist.md
```

### Decision Quality Test
1. Send 5 different message types
2. Verify each gets appropriate action
3. Check reasoning makes sense
4. Verify context is used correctly

---

## Error Handling

```python
# Timeout for thinking (don't get stuck)
async def process_with_timeout(msg, context):
    try:
        async with asyncio.timeout(60):  # 60 second max
            await process_with_thinking(msg, context)
    except asyncio.TimeoutError:
        logger.error("Orchestrator thinking timed out")
        # Fall back to simple response
        await respond_to_discord("I'm still thinking about this. Will update soon.")

# Context file errors
async def load_context_safe():
    try:
        return await load_context()
    except FileNotFoundError as e:
        logger.warning(f"Context file missing: {e}")
        return Context(product="", worklist="", learnings="", ...)
```

---

## Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY services/orchestrator/requirements.txt .
RUN pip install -r requirements.txt

COPY services/orchestrator/ ./services/orchestrator/
COPY shared/ ./shared/

# Context files are mounted as volume
VOLUME /app/context

CMD ["python", "-m", "services.orchestrator.main"]
```

---

## Notes for Builder

- Extended thinking is CRITICAL - this is where strategic decisions happen
- Don't rush the thinking budget - let it reason deeply
- Context loading should be fast (cache if needed)
- Worklist and learnings are append-mostly (don't lose history)
- Log all decisions with full reasoning for debugging
- The Orchestrator should feel "thoughtful" - never hasty
- When in doubt, ask for more context rather than guessing
