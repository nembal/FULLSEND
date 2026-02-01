# PRD: Redis Agent

## Overview

**Role:** The analyst — monitors metrics that FULLSEND defined for each experiment, detects thresholds, surfaces insights to Orchestrator.

**Runtime:** Python daemon with Gemini API
**Model:** Gemini 2.0 Flash (cheap, fast analysis)
**Container:** `fullsend-redis-agent`

---

## Model Setup: Gemini 2.0 Flash

```python
import google.generativeai as genai

genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

model = genai.GenerativeModel("gemini-2.0-flash-exp")

response = model.generate_content(
    "Analyze these metrics...",
    generation_config=genai.GenerationConfig(
        temperature=0.2,
        max_output_tokens=1000,
    )
)
```

### Why Gemini Flash?
- Cheap for continuous monitoring
- Fast responses for real-time alerts
- Good at pattern detection and summarization

---

## Personality

Analytical. Alert. Concise. Spots patterns and anomalies. Reports facts, not opinions. Never cries wolf.

---

## What It Does

1. **Reads metric specs** from FULLSEND's experiment designs
2. **Monitors metrics stream** (`fullsend:metrics`)
3. **Aggregates and calculates** derived metrics
4. **Detects threshold crossings** (success/failure)
5. **Spots anomalies** (unusual patterns)
6. **Alerts Orchestrator** with insights
7. **Generates periodic summaries** (hourly/daily)

## What It Does NOT Do

- Design experiments (that's FULLSEND)
- Decide what metrics matter (that's FULLSEND)
- Take action on insights (that's Orchestrator)

---

## File Structure

```
services/redis_agent/
├── __init__.py
├── main.py           # Entry point (daemon)
├── config.py         # Pydantic settings
├── monitor.py        # Metrics monitoring loop
├── analyzer.py       # LLM-powered analysis
├── alerts.py         # Alert generation
└── prompts/
    ├── analyze.txt   # Analysis prompt
    └── summarize.txt # Summary prompt
```

---

## Dependencies

### Redis Channels
- **Subscribes to:** `fullsend:metrics` (real-time metrics stream)
- **Publishes to:** `fullsend:to_orchestrator` (alerts, insights)

### Redis Keys (Read)
- `metrics_specs:{experiment_id}` — What to monitor
- `experiments:{id}` — Experiment definitions
- `metrics:{experiment_id}` — Raw metrics list

### Redis Keys (Write)
- `metrics_aggregated:{experiment_id}` — Aggregated metrics

### Environment Variables
```
GOOGLE_API_KEY=...
REDIS_URL=redis://redis:6379
REDIS_AGENT_MODEL=gemini-2.0-flash-exp
ALERT_COOLDOWN_SECONDS=300
SUMMARY_INTERVAL_SECONDS=3600
```

---

## Core Logic

### Main Loop (main.py)

```python
import asyncio
from redis.asyncio import Redis

async def main():
    redis = Redis.from_url(REDIS_URL)

    # Start parallel tasks
    await asyncio.gather(
        monitor_metrics_stream(redis),
        run_periodic_summaries(redis),
        check_thresholds_loop(redis),
    )

async def monitor_metrics_stream(redis: Redis):
    """Subscribe to metrics stream and process events."""
    pubsub = redis.pubsub()
    await pubsub.subscribe("fullsend:metrics")

    async for message in pubsub.listen():
        if message["type"] == "message":
            metric = json.loads(message["data"])
            await process_metric(redis, metric)

async def process_metric(redis: Redis, metric: dict):
    """Process a single metric event."""
    exp_id = metric["experiment_id"]

    # Store raw metric
    await redis.rpush(f"metrics:{exp_id}", json.dumps(metric))

    # Update aggregations
    await update_aggregations(redis, exp_id, metric)

    # Check for immediate alerts (e.g., error events)
    if metric.get("event") == "error":
        await send_alert(redis, {
            "type": "error",
            "experiment_id": exp_id,
            "message": metric.get("message", "Unknown error"),
            "severity": "high"
        })
```

### Threshold Checking (monitor.py)

```python
async def check_thresholds_loop(redis: Redis):
    """Periodically check all experiments for threshold crossings."""
    while True:
        experiments = await get_active_experiments(redis)

        for exp in experiments:
            await check_experiment_thresholds(redis, exp)

        await asyncio.sleep(60)  # Check every minute

async def check_experiment_thresholds(redis: Redis, exp: dict):
    """Check if an experiment has crossed success/failure thresholds."""
    exp_id = exp["id"]
    metrics_spec = await get_metrics_spec(redis, exp_id)
    current_metrics = await get_current_metrics(redis, exp_id)

    # Check success criteria
    for criterion in exp.get("success_criteria", []):
        if evaluate_criterion(criterion, current_metrics):
            await send_alert(redis, {
                "type": "success_threshold",
                "experiment_id": exp_id,
                "criterion": criterion,
                "current_value": current_metrics,
                "message": f"Experiment {exp_id} hit success: {criterion}"
            })

    # Check failure criteria
    for criterion in exp.get("failure_criteria", []):
        if evaluate_criterion(criterion, current_metrics):
            await send_alert(redis, {
                "type": "failure_threshold",
                "experiment_id": exp_id,
                "criterion": criterion,
                "current_value": current_metrics,
                "message": f"Experiment {exp_id} hit failure: {criterion}"
            })

def evaluate_criterion(criterion: str, metrics: dict) -> bool:
    """Evaluate a criterion like 'response_rate > 0.10'."""
    # Parse criterion (e.g., "response_rate > 0.10")
    # This is simplified - real impl would be more robust
    parts = criterion.split()
    if len(parts) == 3:
        metric_name, operator, threshold = parts
        value = metrics.get(metric_name, 0)
        threshold = float(threshold)

        if operator == ">":
            return value > threshold
        elif operator == "<":
            return value < threshold
        elif operator == ">=":
            return value >= threshold
        elif operator == "<=":
            return value <= threshold

    return False
```

### LLM Analysis (analyzer.py)

```python
import google.generativeai as genai

async def analyze_experiment_metrics(redis: Redis, exp_id: str) -> str:
    """Use LLM to analyze experiment metrics and generate insights."""

    exp = await get_experiment(redis, exp_id)
    metrics = await get_all_metrics(redis, exp_id)

    prompt = f"""Analyze these experiment metrics and provide insights.

## Experiment
ID: {exp_id}
Hypothesis: {exp.get('hypothesis', 'Unknown')}
Target: {exp.get('target', {}).get('description', 'Unknown')}

## Success Criteria
{format_list(exp.get('success_criteria', []))}

## Failure Criteria
{format_list(exp.get('failure_criteria', []))}

## Current Metrics
{format_metrics(metrics)}

## Task
1. Are we trending toward success or failure?
2. Any anomalies or patterns?
3. Recommendations (if any)?

Be concise. Facts only. No fluff."""

    model = genai.GenerativeModel(REDIS_AGENT_MODEL)
    response = await asyncio.to_thread(
        model.generate_content,
        prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.2,
            max_output_tokens=500,
        )
    )

    return response.text
```

### Alert Sending (alerts.py)

```python
# Track recent alerts to avoid spam
recent_alerts: dict[str, float] = {}

async def send_alert(redis: Redis, alert: dict):
    """Send alert to Orchestrator with cooldown."""

    # Create alert key for deduplication
    alert_key = f"{alert['experiment_id']}:{alert['type']}"

    # Check cooldown
    last_sent = recent_alerts.get(alert_key, 0)
    if time.time() - last_sent < ALERT_COOLDOWN_SECONDS:
        return  # Skip, too soon

    # Update cooldown tracker
    recent_alerts[alert_key] = time.time()

    # Add timestamp and source
    alert["timestamp"] = datetime.now().isoformat()
    alert["source"] = "redis_agent"

    # Publish to Orchestrator
    await redis.publish("fullsend:to_orchestrator", json.dumps(alert))

    logger.info(f"Alert sent: {alert['type']} for {alert['experiment_id']}")
```

### Periodic Summaries (main.py)

```python
async def run_periodic_summaries(redis: Redis):
    """Generate periodic summaries of all experiments."""
    while True:
        await asyncio.sleep(SUMMARY_INTERVAL_SECONDS)

        experiments = await get_active_experiments(redis)

        if not experiments:
            continue

        summary = await generate_summary(redis, experiments)

        await redis.publish("fullsend:to_orchestrator", json.dumps({
            "type": "periodic_summary",
            "source": "redis_agent",
            "timestamp": datetime.now().isoformat(),
            "summary": summary,
            "experiment_count": len(experiments)
        }))

async def generate_summary(redis: Redis, experiments: list) -> str:
    """Generate LLM summary of all active experiments."""

    summaries = []
    for exp in experiments:
        metrics = await get_current_metrics(redis, exp["id"])
        summaries.append(f"- {exp['id']}: {format_metrics_brief(metrics)}")

    prompt = f"""Summarize the status of these experiments in 2-3 sentences.

## Active Experiments
{chr(10).join(summaries)}

Focus on: wins, concerns, and recommendations."""

    model = genai.GenerativeModel(REDIS_AGENT_MODEL)
    response = await asyncio.to_thread(
        model.generate_content,
        prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.2,
            max_output_tokens=200,
        )
    )

    return response.text
```

---

## Alert Types

| Type | Severity | Trigger |
|------|----------|---------|
| `success_threshold` | info | Success criterion met |
| `failure_threshold` | high | Failure criterion met |
| `error` | high | Experiment execution error |
| `anomaly` | medium | Unusual pattern detected |
| `periodic_summary` | info | Scheduled summary |
| `experiment_completed` | info | All runs finished |

---

## Prompts

### prompts/analyze.txt

```
You are an analytics agent monitoring GTM experiments.

Your job is to analyze metrics and surface insights. Be concise and factual.

## Guidelines
- Report what the data shows, not opinions
- Flag anomalies (unusual spikes, drops, patterns)
- Compare to success/failure criteria
- Suggest actions only when data strongly supports them
- Never cry wolf - only alert on significant findings

## Output Format
- Status: [on_track | at_risk | failing | succeeded]
- Key metric: [most important number]
- Insight: [one sentence finding]
- Action: [recommendation if any, otherwise "none"]
```

---

## Acceptance Criteria

- [ ] Connects to Redis on startup
- [ ] Subscribes to `fullsend:metrics` stream
- [ ] Aggregates metrics per experiment
- [ ] Detects success/failure threshold crossings
- [ ] Sends alerts to Orchestrator with cooldown
- [ ] Generates periodic summaries (hourly)
- [ ] Uses Gemini Flash for analysis
- [ ] Handles missing metrics gracefully
- [ ] Doesn't spam alerts (cooldown works)
- [ ] Logs all alerts for debugging

---

## Test Plan

### Basic Test
```bash
# Start Redis Agent
python -m services.redis_agent.main &

# Publish test metrics
redis-cli PUBLISH fullsend:metrics '{"experiment_id": "exp_test", "event": "email_sent", "count": 1}'
redis-cli PUBLISH fullsend:metrics '{"experiment_id": "exp_test", "event": "email_opened", "count": 1}'

# Check aggregations
redis-cli LRANGE metrics:exp_test 0 -1
```

### Threshold Test
```bash
# Create experiment with thresholds
redis-cli HSET experiments:exp_test hypothesis "Test experiment"
redis-cli HSET experiments:exp_test success_criteria '["response_rate > 0.10"]'
redis-cli HSET experiments:exp_test failure_criteria '["response_rate < 0.02"]'

# Publish metrics that cross threshold
redis-cli PUBLISH fullsend:metrics '{"experiment_id": "exp_test", "response_rate": 0.15}'

# Check for alert
redis-cli SUBSCRIBE fullsend:to_orchestrator
# Should see success_threshold alert
```

### Cooldown Test
```bash
# Send same alert trigger twice quickly
redis-cli PUBLISH fullsend:metrics '{"experiment_id": "exp_test", "event": "error", "message": "Test error"}'
sleep 1
redis-cli PUBLISH fullsend:metrics '{"experiment_id": "exp_test", "event": "error", "message": "Test error"}'

# Should only see ONE alert (second is within cooldown)
```

---

## Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY services/redis_agent/requirements.txt .
RUN pip install -r requirements.txt

COPY services/redis_agent/ ./services/redis_agent/
COPY shared/ ./shared/

ENV GOOGLE_API_KEY=""
ENV REDIS_URL="redis://redis:6379"

CMD ["python", "-m", "services.redis_agent.main"]
```

---

## Notes for Builder

- Keep it simple — monitor, detect, alert
- Gemini Flash is cheap, use it for analysis
- Cooldown is critical — no alert spam
- Store aggregations for historical analysis
- Threshold evaluation should be robust (handle edge cases)
- Summaries are for humans — make them readable
- Log everything for debugging
