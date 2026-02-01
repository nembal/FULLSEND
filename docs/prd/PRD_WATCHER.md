# PRD: Watcher

## Overview

**Role:** The receptionist — filters Discord noise, answers simple queries, escalates important stuff to Orchestrator.

**Runtime:** Python daemon with Google Gemini API
**Model:** Gemini 2.0 Flash (cheap, fast, 1M context)
**Container:** `fullsend-watcher`

---

## Model Setup: Gemini 2.0 Flash

### Installation
```bash
pip install google-generativeai
```

### API Key
Get from: https://aistudio.google.com/apikey

### Environment
```bash
GOOGLE_API_KEY=your_api_key_here
WATCHER_MODEL=gemini-2.0-flash-exp  # or gemini-2.0-flash when GA
```

### Basic Usage
```python
import google.generativeai as genai

genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

model = genai.GenerativeModel("gemini-2.0-flash-exp")

response = model.generate_content(
    "Classify this message: ...",
    generation_config=genai.GenerationConfig(
        temperature=0.1,  # Low temp for classification
        max_output_tokens=500,
    )
)

print(response.text)
```

### Why Gemini Flash?
- **Cost:** ~$0.075/1M input tokens (10x cheaper than Haiku)
- **Speed:** Sub-second responses
- **Context:** 1M tokens (can hold lots of history if needed)
- **Quality:** Excellent at classification tasks

---

## Personality

Helpful but knows its place. Quick to answer simple stuff, quick to escalate important stuff. Never makes strategic decisions.

---

## What It Does

1. **Monitors** all Discord messages in real-time via Redis channel
2. **Classifies** each message: ignore / answer / escalate
3. **Answers** simple status questions without waking Orchestrator
4. **Escalates** important messages to Orchestrator with context
5. **Summarizes** channel activity periodically (optional)

## What It Does NOT Do

- Make strategic decisions
- Dispatch work to other agents
- Design experiments
- Modify any state

---

## File Structure

```
services/watcher/
├── __init__.py
├── main.py           # Entry point (daemon loop)
├── config.py         # Pydantic settings
├── classifier.py     # Message classification logic
├── responder.py      # Simple response generation
└── prompts/
    ├── classify.txt  # Classification prompt
    └── respond.txt   # Simple response prompt
```

---

## Dependencies

### Redis Channels
- **Subscribes to:** `fullsend:discord_raw`
- **Publishes to:**
  - `fullsend:to_orchestrator` (escalations only)
  - `fullsend:from_orchestrator` (simple responses back to Discord)

### Python Packages
```
google-generativeai
redis
pydantic
pydantic-settings
```

### Environment Variables
```
GOOGLE_API_KEY=...
REDIS_URL=redis://redis:6379
WATCHER_MODEL=gemini-2.0-flash-exp
```

---

## Core Logic

### Main Loop (main.py)

```python
async def main():
    redis = Redis.from_url(REDIS_URL)
    pubsub = redis.pubsub()
    await pubsub.subscribe("fullsend:discord_raw")

    async for message in pubsub.listen():
        if message["type"] == "message":
            data = json.loads(message["data"])
            await process_message(data)

async def process_message(msg: dict):
    # 1. Classify the message
    classification = await classify(msg)

    # 2. Route based on classification
    if classification.action == "ignore":
        return  # Do nothing

    elif classification.action == "answer":
        response = await generate_simple_response(msg, classification)
        await publish("fullsend:from_orchestrator", {
            "type": "watcher_response",
            "channel_id": msg["channel_id"],
            "content": response
        })

    elif classification.action == "escalate":
        await publish("fullsend:to_orchestrator", {
            "type": "escalation",
            "source": "watcher",
            "original_message": msg,
            "reason": classification.reason,
            "priority": classification.priority
        })
```

### Classification Logic (classifier.py)

```python
import google.generativeai as genai

genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

class Classification(BaseModel):
    action: Literal["ignore", "answer", "escalate"]
    reason: str
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    can_answer: Optional[str] = None  # If action=answer, suggested response

async def classify(msg: dict) -> Classification:
    prompt = load_prompt("classify.txt").format(
        username=msg["username"],
        content=msg["content"],
        channel=msg["channel_name"],
        has_mention=msg.get("mentions_bot", False)
    )

    model = genai.GenerativeModel(WATCHER_MODEL)

    response = await asyncio.to_thread(
        model.generate_content,
        prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.1,
            max_output_tokens=500,
        )
    )

    return parse_classification(response.text)
```

### Escalation Criteria

**ALWAYS escalate:**
- Direct @mention of bot
- Keywords: "urgent", "broken", "stop", "help", "error", "failed"
- Explicit commands starting with `/`
- Questions Watcher can't answer from context

**ANSWER directly (don't escalate):**
- "What's the status?" → Read from Redis, respond
- "Is it running?" → Check system state, respond
- "How many experiments?" → Count from Redis, respond
- Generic greetings → Friendly response

**IGNORE:**
- Off-topic chatter
- Messages in non-monitored channels
- Bot's own messages
- Reactions/emoji-only messages

---

## Prompts

### prompts/classify.txt

```
You are Watcher, a message filter for the Fullsend GTM agent system.

Your job: Decide what to do with each Discord message.

## Message
Username: {{username}}
Channel: {{channel}}
Bot mentioned: {{has_mention}}
Content: {{content}}

## Your Options

1. **IGNORE** - Off-topic, chatter, not relevant to the system
2. **ANSWER** - Simple question you can answer (status, counts, basic info)
3. **ESCALATE** - Important, needs Orchestrator attention (ideas, problems, requests)

## Escalation Triggers (ALWAYS escalate these)
- Direct @mention of bot
- Keywords: urgent, broken, stop, help, error, failed, idea
- Requests for action ("can you...", "please...", "I want...")
- New GTM ideas or suggestions
- Questions about strategy or experiments

## Things You Can Answer
- "What's the status?" - System is running/paused
- "How many experiments?" - Count active experiments
- "Is it working?" - Basic health check
- Simple greetings

## Response Format
Return JSON:
{
  "action": "ignore" | "answer" | "escalate",
  "reason": "Brief explanation",
  "priority": "low" | "medium" | "high" | "urgent",
  "suggested_response": "If action=answer, what to say"
}
```

### prompts/respond.txt

```
You are Watcher, the friendly receptionist for Fullsend.

Generate a brief, helpful response to this simple query.

Query: {{query}}
System Status: {{status}}
Active Experiments: {{experiment_count}}

Keep it short (1-2 sentences). Be friendly but concise.
Don't make promises about what the system will do.
If unsure, say you'll escalate to the Orchestrator.
```

---

## Redis Data Access

Watcher can READ (not write) these keys for answering simple queries:

```python
# System status
status = await redis.get("fullsend:status")  # "running" | "paused"

# Experiment counts
experiment_keys = await redis.keys("experiments:*")
active_count = len([k for k in experiment_keys if await redis.hget(k, "state") == "running"])

# Recent activity
recent_runs = await redis.lrange("fullsend:recent_runs", 0, 5)
```

---

## Message Format

### Incoming (from Discord Service)
```json
{
  "type": "discord_message",
  "message_id": "123456789",
  "channel_id": "987654321",
  "channel_name": "gtm-ideas",
  "username": "jake",
  "user_id": "111222333",
  "content": "What if we scraped GitHub stargazers?",
  "mentions_bot": false,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Outgoing Escalation (to Orchestrator)
```json
{
  "type": "escalation",
  "source": "watcher",
  "priority": "high",
  "reason": "New GTM idea from user",
  "original_message": { ... },
  "context": {
    "channel": "gtm-ideas",
    "user": "jake",
    "summary": "User suggests scraping GitHub stargazers"
  }
}
```

### Outgoing Response (to Discord)
```json
{
  "type": "watcher_response",
  "channel_id": "987654321",
  "reply_to": "123456789",
  "content": "We're currently running 3 active experiments. All systems healthy!"
}
```

---

## Acceptance Criteria

- [ ] Connects to Redis on startup
- [ ] Subscribes to `fullsend:discord_raw` channel
- [ ] Classifies messages using Haiku
- [ ] Ignores off-topic messages (no action taken)
- [ ] Answers simple status queries without escalating
- [ ] Escalates important messages to `fullsend:to_orchestrator`
- [ ] Includes proper context in escalations
- [ ] Responds within 2 seconds for simple queries
- [ ] Handles Redis disconnection gracefully (reconnect)
- [ ] Logs all classifications for debugging

---

## Test Plan

### Unit Tests
```bash
# Test classification
echo '{"content": "What is the status?", "username": "test"}' | python -m services.watcher.classifier
# Expected: action=answer

echo '{"content": "I have an idea for scraping LinkedIn", "username": "test"}' | python -m services.watcher.classifier
# Expected: action=escalate
```

### Integration Test
```bash
# Start watcher
python -m services.watcher.main &

# Publish test message
redis-cli PUBLISH fullsend:discord_raw '{"type":"discord_message","content":"status?","username":"test","channel_id":"123"}'

# Check for response
redis-cli SUBSCRIBE fullsend:from_orchestrator
# Should see watcher_response within 2 seconds
```

### Manual Test
1. Send "What's the status?" in Discord
2. Watcher should respond directly (no Orchestrator involved)
3. Send "I have an idea: scrape YC founders"
4. Watcher should escalate to Orchestrator (check logs)

---

## Error Handling

```python
# Retry logic for Gemini API
@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def classify_with_retry(msg):
    return await classify(msg)

# Fallback if classification fails
async def process_message_safe(msg):
    try:
        classification = await classify_with_retry(msg)
    except Exception as e:
        # When in doubt, escalate
        logger.error(f"Classification failed: {e}")
        await escalate(msg, reason="Classification error - needs human review")
```

---

## Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY services/watcher/requirements.txt .
RUN pip install -r requirements.txt

COPY services/watcher/ ./services/watcher/
COPY shared/ ./shared/

CMD ["python", "-m", "services.watcher.main"]
```

---

## Notes for Builder

- Keep it simple - Watcher should be fast and cheap
- Gemini Flash is perfect - fast, cheap, great at classification
- When in doubt, escalate (better to over-escalate than miss important stuff)
- Don't cache classifications - each message is unique
- Log everything for debugging
- Gemini has async support via `asyncio.to_thread()` wrapper
