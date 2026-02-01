# PRD: Executor

## Overview

**Role:** The workhorse — executes scheduled experiments by running tools with specified parameters. No AI, just reliable execution.

**Runtime:** Python worker pool with cron scheduling
**Model:** None (runs tools, doesn't think)
**Container:** `fullsend-executor`

---

## Personality

Reliable. Tireless. Reports everything. Does exactly what it's told, no more, no less. Never makes decisions — just executes.

---

## What It Does

1. **Watches schedule triggers** (cron or continuous loop)
2. **Pulls experiment definitions** from Redis
3. **Loads required tools** from the tools directory
4. **Executes tools** with specified parameters
5. **Streams metrics** to Redis for Redis Agent to monitor
6. **Reports completion/failure** back to system

## What It Does NOT Do

- Make decisions about what to run
- Modify experiments
- Choose parameters
- Skip or prioritize (runs everything on schedule)

---

## File Structure

```
services/executor/
├── __init__.py
├── main.py           # Entry point (scheduler + worker)
├── config.py         # Pydantic settings
├── scheduler.py      # Cron/continuous scheduling
├── runner.py         # Tool execution logic
├── metrics.py        # Metrics emission
└── loader.py         # Dynamic tool loading
```

---

## Dependencies

### Redis Channels
- **Subscribes to:** `fullsend:schedules` (schedule updates)
- **Publishes to:**
  - `fullsend:metrics` (real-time metrics stream)
  - `fullsend:experiment_results` (completion/failure)

### Redis Keys (Read)
- `experiments:{id}` — Experiment definitions
- `tools:{name}` — Tool registry (metadata)
- `schedules:{experiment_id}` — Cron expressions

### Redis Keys (Write)
- `experiment_runs:{id}:{timestamp}` — Run results

### Filesystem
- `tools/` — Python tool modules to import and run

### Python Packages
```
redis
pydantic
pydantic-settings
croniter
importlib
```

### Environment Variables
```
REDIS_URL=redis://redis:6379
TOOLS_PATH=/app/tools
SCHEDULE_MODE=trigger  # trigger | cron | speedrun
SPEEDRUN_INTERVAL=5    # seconds between runs in speedrun mode
```

---

## Core Logic

### Main Loop (main.py)

```python
async def main():
    config = load_config()
    redis = Redis.from_url(REDIS_URL)

    if config.schedule_mode == "speedrun":
        # Continuous loop for demo
        await run_speedrun_loop(redis, config.speedrun_interval)
    elif config.schedule_mode == "cron":
        # Traditional cron scheduling
        await run_cron_scheduler(redis)
    else:
        # Trigger mode - wait for Redis messages
        await run_trigger_mode(redis)

async def run_speedrun_loop(redis: Redis, interval: int):
    """Demo mode: run experiments continuously."""
    while True:
        # Get all ready experiments
        experiments = await get_ready_experiments(redis)

        for exp in experiments[:3]:  # Max 3 per cycle
            await execute_experiment(redis, exp)

        await asyncio.sleep(interval)

async def run_cron_scheduler(redis: Redis):
    """Production mode: respect cron schedules."""
    schedules = await load_all_schedules(redis)

    while True:
        now = datetime.now()

        for exp_id, cron_expr in schedules.items():
            if should_run_now(cron_expr, now):
                exp = await get_experiment(redis, exp_id)
                await execute_experiment(redis, exp)

        # Check for schedule updates
        schedules = await load_all_schedules(redis)

        await asyncio.sleep(60)  # Check every minute

async def run_trigger_mode(redis: Redis):
    """Wait for explicit trigger via Redis channel."""
    pubsub = redis.pubsub()
    await pubsub.subscribe("fullsend:execute_now")

    async for message in pubsub.listen():
        if message["type"] == "message":
            data = json.loads(message["data"])
            exp = await get_experiment(redis, data["experiment_id"])
            await execute_experiment(redis, exp)
```

### Tool Loader (loader.py)

```python
import importlib.util
from pathlib import Path

def load_tool(tool_name: str) -> callable:
    """Dynamically load a tool from the tools directory."""

    tool_path = Path(TOOLS_PATH) / f"{tool_name}.py"

    if not tool_path.exists():
        raise ToolNotFoundError(f"Tool not found: {tool_name}")

    # Load the module
    spec = importlib.util.spec_from_file_location(tool_name, tool_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Get the main function (convention: same name as file)
    if not hasattr(module, tool_name):
        # Try 'run' as fallback
        if hasattr(module, 'run'):
            return module.run
        raise ToolError(f"Tool {tool_name} has no callable function")

    return getattr(module, tool_name)

def get_tool_metadata(tool_name: str) -> dict:
    """Get tool metadata from Redis registry."""
    return redis.hgetall(f"tools:{tool_name}")
```

### Experiment Runner (runner.py)

```python
async def execute_experiment(redis: Redis, experiment: dict):
    """Execute a single experiment run."""

    exp_id = experiment["id"]
    run_id = f"{exp_id}:{int(time.time())}"

    logger.info(f"Starting experiment run: {run_id}")

    # Update experiment state
    await redis.hset(f"experiments:{exp_id}", "state", "running")

    try:
        # Load the required tool
        tool_name = experiment["execution"]["tool"]
        tool_fn = load_tool(tool_name)

        # Get parameters
        params = experiment["execution"].get("params", {})

        # Execute with metrics collection
        start_time = time.time()

        result = await run_with_metrics(
            redis, exp_id, run_id,
            lambda: tool_fn(**params)
        )

        duration = time.time() - start_time

        # Save run results
        await save_run_result(redis, run_id, {
            "status": "completed",
            "duration_seconds": duration,
            "result_summary": summarize_result(result),
            "timestamp": datetime.now().isoformat()
        })

        # Update experiment state
        await redis.hset(f"experiments:{exp_id}", "state", "run")

        # Notify completion
        await publish_result(redis, {
            "type": "experiment_completed",
            "experiment_id": exp_id,
            "run_id": run_id,
            "status": "success",
            "duration": duration
        })

    except Exception as e:
        logger.error(f"Experiment failed: {e}")

        # Save failure
        await save_run_result(redis, run_id, {
            "status": "failed",
            "error": str(e),
            "error_type": type(e).__name__,
            "timestamp": datetime.now().isoformat()
        })

        # Update experiment state
        await redis.hset(f"experiments:{exp_id}", "state", "failed")

        # Notify failure
        await publish_result(redis, {
            "type": "experiment_failed",
            "experiment_id": exp_id,
            "run_id": run_id,
            "error": str(e),
            "error_type": type(e).__name__
        })
```

### Metrics Emission (metrics.py)

```python
async def run_with_metrics(
    redis: Redis,
    exp_id: str,
    run_id: str,
    fn: callable
) -> Any:
    """Run a function while emitting metrics."""

    # Emit start metric
    await emit_metric(redis, exp_id, {
        "event": "run_started",
        "run_id": run_id,
        "timestamp": time.time()
    })

    # Run the tool
    result = fn()

    # If result is iterable (e.g., list of emails sent), emit progress
    if hasattr(result, '__iter__') and not isinstance(result, (str, dict)):
        result = list(result)  # Materialize

        await emit_metric(redis, exp_id, {
            "event": "items_processed",
            "count": len(result),
            "run_id": run_id
        })

    # Emit completion metric
    await emit_metric(redis, exp_id, {
        "event": "run_completed",
        "run_id": run_id,
        "timestamp": time.time()
    })

    return result

async def emit_metric(redis: Redis, exp_id: str, metric: dict):
    """Emit a metric to the metrics stream."""

    metric["experiment_id"] = exp_id

    # Publish to stream for Redis Agent
    await redis.publish("fullsend:metrics", json.dumps(metric))

    # Also append to experiment's metrics list
    await redis.rpush(f"metrics:{exp_id}", json.dumps(metric))
```

### Scheduler (scheduler.py)

```python
from croniter import croniter

def should_run_now(cron_expr: str, now: datetime) -> bool:
    """Check if a cron expression matches the current time."""

    cron = croniter(cron_expr, now - timedelta(minutes=1))
    next_run = cron.get_next(datetime)

    # Within 1 minute window
    return abs((next_run - now).total_seconds()) < 60

async def load_all_schedules(redis: Redis) -> dict[str, str]:
    """Load all experiment schedules from Redis."""

    schedules = {}

    async for key in redis.scan_iter("schedules:*"):
        exp_id = key.split(":")[-1]
        cron_expr = await redis.get(key)

        # Only include ready experiments
        state = await redis.hget(f"experiments:{exp_id}", "state")
        if state == "ready":
            schedules[exp_id] = cron_expr

    return schedules
```

---

## Message Formats

### Schedule Update (incoming)
```json
{
  "experiment_id": "exp_20240115_github_stars",
  "schedule": "0 9 * * MON",
  "timezone": "America/Los_Angeles"
}
```

### Metrics (outgoing)
```json
{
  "experiment_id": "exp_20240115_github_stars",
  "run_id": "exp_20240115_github_stars:1705320000",
  "event": "items_processed",
  "count": 150,
  "timestamp": 1705320123.456
}
```

### Completion (outgoing)
```json
{
  "type": "experiment_completed",
  "experiment_id": "exp_20240115_github_stars",
  "run_id": "exp_20240115_github_stars:1705320000",
  "status": "success",
  "duration": 45.2,
  "result_summary": {
    "emails_sent": 150,
    "leads_found": 180
  }
}
```

### Failure (outgoing)
```json
{
  "type": "experiment_failed",
  "experiment_id": "exp_20240115_github_stars",
  "run_id": "exp_20240115_github_stars:1705320000",
  "error": "Rate limited by GitHub API",
  "error_type": "RateLimitError",
  "partial_results": {
    "emails_sent": 50
  }
}
```

---

## Tool Contract

Tools must follow this contract to work with Executor:

```python
# tools/example_tool.py

def example_tool(param1: str, param2: int = 10) -> dict:
    """
    Tool description.

    Args:
        param1: Description
        param2: Description (optional)

    Returns:
        Dictionary with results
    """

    # Do the work
    results = []

    for i in range(param2):
        # Process...
        results.append({"id": i, "status": "done"})

    return {
        "items": results,
        "count": len(results),
        "success": True
    }
```

**Requirements:**
- Function name matches filename (or provide `run` function)
- Accept parameters as keyword arguments
- Return a dict with results
- Raise exceptions on failure (don't return error codes)
- Handle partial success (return what you can)

---

## Schedule Modes

### 1. Trigger Mode (default)
Wait for explicit execution requests via Redis channel.

```bash
# Trigger an experiment
redis-cli PUBLISH fullsend:execute_now '{"experiment_id": "exp_123"}'
```

### 2. Cron Mode
Respect cron schedules defined in `schedules:{experiment_id}`.

```bash
SCHEDULE_MODE=cron python -m services.executor.main
```

### 3. Speedrun Mode (Demo)
Run experiments continuously with a short interval.

```bash
SCHEDULE_MODE=speedrun SPEEDRUN_INTERVAL=5 python -m services.executor.main
```

---

## Acceptance Criteria

- [ ] Connects to Redis on startup
- [ ] Loads tools dynamically from `tools/` directory
- [ ] Supports all three schedule modes (trigger, cron, speedrun)
- [ ] Executes experiments with correct parameters
- [ ] Emits metrics to `fullsend:metrics` stream
- [ ] Reports completion to `fullsend:experiment_results`
- [ ] Reports failures with error details
- [ ] Updates experiment state in Redis
- [ ] Saves run results to `experiment_runs:{id}:{ts}`
- [ ] Handles tool not found gracefully
- [ ] Handles tool execution errors gracefully
- [ ] Doesn't hang on failed tools (timeout)

---

## Test Plan

### Unit Tests
```bash
# Test tool loader
python -m services.executor.loader --test tools/resend_email.py

# Test cron parser
python -m services.executor.scheduler --test "0 9 * * MON"
```

### Integration Test
```bash
# Create a simple test tool
echo 'def test_tool(): return {"status": "ok"}' > tools/test_tool.py

# Create experiment in Redis
redis-cli HSET experiments:exp_test tool test_tool state ready
redis-cli SET schedules:exp_test "* * * * *"

# Start executor in cron mode
SCHEDULE_MODE=cron python -m services.executor.main &

# Wait 1 minute, check for results
sleep 65
redis-cli KEYS experiment_runs:exp_test:*
# Should show a run result
```

### Speedrun Test
```bash
# Start in speedrun mode
SCHEDULE_MODE=speedrun SPEEDRUN_INTERVAL=2 python -m services.executor.main &

# Watch metrics stream
redis-cli SUBSCRIBE fullsend:metrics
# Should see metrics every 2 seconds
```

---

## Error Handling

```python
# Tool execution timeout
async def execute_with_timeout(tool_fn, params, timeout=300):
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(tool_fn, **params),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        raise ToolTimeoutError(f"Tool execution exceeded {timeout}s")

# Partial results on failure
async def run_with_recovery(redis, exp_id, tool_fn, params):
    try:
        return tool_fn(**params)
    except Exception as e:
        # Try to get partial results
        if hasattr(e, 'partial_results'):
            await emit_metric(redis, exp_id, {
                "event": "partial_completion",
                "items_processed": len(e.partial_results)
            })
            return e.partial_results
        raise

# Retry transient failures
TRANSIENT_ERRORS = (ConnectionError, TimeoutError)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=1, max=30),
    retry=retry_if_exception_type(TRANSIENT_ERRORS)
)
async def execute_with_retry(tool_fn, params):
    return tool_fn(**params)
```

---

## Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY services/executor/requirements.txt .
RUN pip install -r requirements.txt

COPY services/executor/ ./services/executor/
COPY shared/ ./shared/

# Tools are mounted as volume
VOLUME /app/tools

# Configuration via environment
ENV SCHEDULE_MODE=trigger
ENV SPEEDRUN_INTERVAL=5

CMD ["python", "-m", "services.executor.main"]
```

---

## Config File Support

Executor can also read from `config/schedule.yaml`:

```yaml
mode: speedrun  # trigger | cron | speedrun

trigger:
  channels:
    - fullsend:execute_now

cron:
  check_interval: 60  # seconds

speedrun:
  interval_seconds: 5
  max_experiments_per_cycle: 3

timeouts:
  tool_execution: 300  # seconds

retry:
  max_attempts: 3
  backoff_min: 1
  backoff_max: 30
```

---

## Notes for Builder

- This is the simplest service — no AI, just Python
- Dynamic tool loading is the core feature
- Make sure timeouts work (don't let bad tools hang forever)
- Metrics streaming is important for Redis Agent to work
- Speedrun mode is critical for hackathon demo
- Tools should be isolated — one bad tool shouldn't crash Executor
- Log everything — this is where experiments actually run
- Consider running tools in subprocess for isolation (optional)
