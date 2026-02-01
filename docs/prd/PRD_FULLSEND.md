# PRD: FULLSEND

## Overview

**Role:** The creative strategist — designs experiments, defines success metrics, sets schedules. Has access to tools/skills it can use or request. This is where GTM ideas become executable experiment specs.

**Runtime:** Python service that spawns Claude Code in RALPH loops
**Model:** Claude Code CLI (Sonnet/Opus) spawning more Claude Codes
**Container:** `fullsend-brain`

---

## Architecture: RALPH Loops

FULLSEND uses the **RALPH pattern** — a task loop where Claude Code iterates through tasks with persistent memory.

```
┌─────────────────────────────────────────────────────────────┐
│                      FULLSEND Service                        │
│                                                              │
│  1. Receive experiment request from Orchestrator             │
│  2. Create TASKS.md for this experiment                      │
│  3. Create STATUS.md for context/memory                      │
│  4. Spawn Claude Code in RALPH loop                          │
│  5. Claude Code iterates: task → do → mark done → next       │
│  6. Collect results, publish experiment spec                 │
└─────────────────────────────────────────────────────────────┘

RALPH Loop:
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  Read    │────→│  Do      │────→│  Update  │────→│  Mark    │
│ TASKS.md │     │  Task    │     │STATUS.md │     │  Done    │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
      ↑                                                  │
      └──────────────────────────────────────────────────┘
                         (loop until all done)
```

### Why RALPH?
- **Memory**: STATUS.md persists context between iterations
- **Reliability**: Each task is atomic, can retry on failure
- **Observability**: TASKS.md shows progress in real-time
- **Composability**: Claude Code can spawn MORE Claude Codes for subtasks

---

## Personality

Bold. Creative. Experimental. Commits fully to ideas. Learns fast from results. Doesn't overthink — ships experiments and iterates.

---

## What It Does

1. **Receives experiment requests** from Orchestrator
2. **Designs complete experiment specs:**
   - Hypothesis
   - Target audience
   - Outreach approach
   - Metrics to track (what Redis Agent monitors)
   - Success/failure criteria
   - Schedule/cadence
3. **Checks available tools** — uses existing or requests new ones
4. **Sets cron triggers** for Executor
5. **Can run simple experiments directly** (has Claude Code tools)
6. **Requests new tools** from Builder when needed
7. **Writes tactical learnings** ("Template A got 20% response rate")

## What It Does NOT Do

- Strategic prioritization (that's Orchestrator)
- Build tools from scratch (that's Builder)
- Run scheduled experiments (that's Executor)

---

## File Structure

```
services/fullsend/
├── __init__.py
├── main.py           # Entry point (listens for requests)
├── config.py         # Pydantic settings
├── spawner.py        # Claude Code subprocess spawner
├── experiment.py     # Experiment spec generation
├── skills/           # Built-in skills available to Claude Code
│   ├── __init__.py
│   ├── redis_tools.py    # Read/write Redis
│   ├── file_tools.py     # Read/write files
│   └── browserbase.py    # Web research
└── prompts/
    └── system.txt    # System prompt for Claude Code
```

---

## Dependencies

### Redis Channels
- **Subscribes to:** `fullsend:to_fullsend`
- **Publishes to:**
  - `fullsend:experiments` (new experiment specs)
  - `fullsend:builder_requests` (tool PRDs for Builder)
  - `fullsend:schedules` (cron schedules for Executor)
  - `fullsend:to_orchestrator` (status updates, completions)

### Redis Keys (Read/Write)
- `experiments:{id}` — Experiment definitions
- `metrics_specs:{experiment_id}` — Metrics to track
- `learnings:tactical:*` — Tactical learnings
- `tools:*` — Available tools registry

### Filesystem Access
- `tools/` — Built tools (can import and use)
- `context/` — Product context, learnings (read-only)

### Environment Variables
```
ANTHROPIC_API_KEY=...
REDIS_URL=redis://redis:6379
FULLSEND_MODEL=claude-sonnet-4-20250514
TOOLS_PATH=/app/tools
CONTEXT_PATH=/app/context
```

---

## Core Logic

### Main Loop (main.py)

```python
async def main():
    redis = Redis.from_url(REDIS_URL)
    pubsub = redis.pubsub()
    await pubsub.subscribe("fullsend:to_fullsend")

    async for message in pubsub.listen():
        if message["type"] == "message":
            data = json.loads(message["data"])
            await handle_request(data)

async def handle_request(request: dict):
    """Handle an experiment request from Orchestrator."""

    if request["type"] == "experiment_request":
        await design_experiment(request)
    elif request["type"] == "tool_feedback":
        await handle_tool_feedback(request)
    elif request["type"] == "run_direct":
        await run_experiment_directly(request)
```

### RALPH Loop Spawner (spawner.py)

```python
import subprocess
import tempfile
from pathlib import Path
import shutil

class RalphLoop:
    """RALPH-style task loop for Claude Code."""

    def __init__(self, work_dir: Path, max_iterations: int = 50):
        self.work_dir = work_dir
        self.max_iterations = max_iterations
        self.tasks_file = work_dir / "TASKS.md"
        self.status_file = work_dir / "STATUS.md"

    def setup(self, tasks: list[str], initial_context: str):
        """Initialize TASKS.md and STATUS.md."""
        self.work_dir.mkdir(parents=True, exist_ok=True)

        # Write TASKS.md
        tasks_content = "# Tasks\n\n"
        for i, task in enumerate(tasks, 1):
            tasks_content += f"- [ ] TASK-{i:03d}: {task}\n"
        self.tasks_file.write_text(tasks_content)

        # Write STATUS.md
        self.status_file.write_text(f"# Status (Memory)\n\n{initial_context}\n\n## Log\n")

    def get_next_task(self) -> str | None:
        """Get next uncompleted task."""
        content = self.tasks_file.read_text()
        for line in content.split("\n"):
            if line.startswith("- [ ] TASK-"):
                return line.split(":")[0].replace("- [ ] ", "").strip()
        return None

    async def run(self) -> str:
        """Run the RALPH loop until all tasks complete."""

        for iteration in range(self.max_iterations):
            task_id = self.get_next_task()

            if not task_id:
                # All done!
                return self.status_file.read_text()

            print(f"RALPH iteration {iteration + 1}: {task_id}")

            prompt = f"""You are completing task {task_id} from TASKS.md.

Read TASKS.md to find your task.
Read STATUS.md for context from previous tasks (memory).

Do the task. When done:
1. Update STATUS.md with what you did
2. Mark task done: change `- [ ] {task_id}:` to `- [x] {task_id}:` in TASKS.md
3. Output: **TASK_DONE**"""

            # Spawn Claude Code for this iteration
            result = subprocess.run(
                [
                    "claude",
                    "-p", prompt,
                    "--allowedTools", "Edit,Bash,Write,Read,Glob,Grep",
                    "--dangerously-skip-permissions"
                ],
                cwd=self.work_dir,
                capture_output=True,
                text=True,
                timeout=300,
                env={**os.environ, "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY}
            )

            if "TASK_DONE" not in result.stdout:
                print(f"Warning: {task_id} may not have completed")

            await asyncio.sleep(2)  # Brief pause between iterations

        raise RuntimeError(f"Hit max iterations ({self.max_iterations})")

async def spawn_ralph_loop(
    tasks: list[str],
    context: str,
    work_dir: Path = None
) -> str:
    """Spawn a RALPH loop and return results."""

    if work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="fullsend_"))

    try:
        loop = RalphLoop(work_dir)
        loop.setup(tasks, context)
        return await loop.run()
    finally:
        # Cleanup temp dir (optional - might want to keep for debugging)
        # shutil.rmtree(work_dir)
        pass
```

### Simple Spawn (for quick tasks)

```python
async def spawn_claude_code(
    prompt: str,
    working_dir: Path = Path("/app"),
    timeout: int = 300
) -> str:
    """Spawn Claude Code for a single task (no loop)."""

    result = subprocess.run(
        [
            "claude",
            "-p", prompt,
            "--allowedTools", "Edit,Bash,Write,Read,Glob,Grep",
            "--dangerously-skip-permissions"
        ],
        cwd=working_dir,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ, "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY}
    )

    if result.returncode != 0:
        raise RuntimeError(f"Claude Code failed: {result.stderr}")

    return result.stdout
```

### Experiment Design (experiment.py)

```python
async def design_experiment(request: dict):
    """Design an experiment spec using RALPH loop."""

    idea = request["idea"]
    context = request.get("context", "")
    available_tools = await get_available_tools()
    recent_learnings = await get_tactical_learnings()

    # Break experiment design into RALPH tasks
    tasks = [
        "Research the target audience and validate the idea is feasible",
        "Check available tools and identify what's needed",
        "Design the experiment spec with hypothesis and metrics",
        "Write the outreach template (actual copy, not placeholders)",
        "Define success/failure criteria and schedule",
        "Output final experiment YAML to experiment_spec.yaml"
    ]

    initial_context = f"""## Experiment Request
{idea}

## Context from Orchestrator
{context}

## Available Tools
{format_tools(available_tools)}

## Recent Learnings
{format_learnings(recent_learnings)}
"""

    # Run RALPH loop
    work_dir = Path(f"/tmp/fullsend/exp_{int(time.time())}")
    result = await spawn_ralph_loop(tasks, initial_context, work_dir)

    # Read the generated experiment spec
    spec_file = work_dir / "experiment_spec.yaml"
    if spec_file.exists():
        experiment_spec = yaml.safe_load(spec_file.read_text())
    else:
        raise RuntimeError("RALPH loop did not produce experiment spec")

    # ... rest of processing
```

### Alternative: Single-Shot Design (for simple experiments)

For simple experiments, skip RALPH and use direct spawn:

```python
async def design_simple_experiment(request: dict):
    """Design a simple experiment without RALPH loop."""

    prompt = f"""
# Design an Experiment

## The Idea
{idea}

## Context from Orchestrator
{context}

## Available Tools
{format_tools(available_tools)}

## Recent Tactical Learnings
{format_learnings(recent_learnings)}

## Your Task

Design a complete experiment specification. Output YAML format:

```yaml
experiment:
  id: exp_YYYYMMDD_short_name
  hypothesis: "What we're testing"

  target:
    description: "Who we're targeting"
    size: estimated_count
    source: "Where we'll get them"

  execution:
    tool: tool_name_to_use
    params:
      key: value
    schedule: "cron expression"

  outreach:
    channel: "email" | "linkedin" | "twitter"
    template: |
      The actual message template with {{variables}}

  metrics:
    - name: metric_name
      type: counter | percentage | duration
      success_threshold: value

  success_criteria:
    - condition 1
    - condition 2

  failure_criteria:
    - condition 1
```

If you need a tool that doesn't exist, also output:

```yaml
tool_request:
  name: tool_name
  description: "What it does"
  inputs:
    - name: param_name
      type: string | integer | list
  outputs:
    - name: output_name
      type: type
  requirements:
    - requirement 1
```

Be bold. Be specific. Include actual email templates, not placeholders.
"""

    # Spawn Claude Code to do the work
    output = await spawn_claude_code(prompt)

    # Parse the YAML output
    experiment_spec = parse_experiment_yaml(output)
    tool_request = parse_tool_request_yaml(output)

    # Save experiment to Redis
    await save_experiment(experiment_spec)

    # Request new tool if needed
    if tool_request:
        await publish("fullsend:builder_requests", tool_request)

    # Set up schedule
    await publish("fullsend:schedules", {
        "experiment_id": experiment_spec["id"],
        "schedule": experiment_spec["execution"]["schedule"]
    })

    # Notify Orchestrator
    await publish("fullsend:to_orchestrator", {
        "type": "experiment_ready",
        "source": "fullsend",
        "experiment_id": experiment_spec["id"],
        "summary": experiment_spec["hypothesis"],
        "needs_tool": tool_request is not None
    })
```

---

## Experiment Spec Format

```yaml
experiment:
  id: exp_20240115_github_stars
  hypothesis: "CTOs who starred competitor repos are high-intent prospects"
  created_at: "2024-01-15T10:30:00Z"
  state: draft  # draft | ready | running | completed | failed | archived

  target:
    description: "CTOs and technical founders who starred competitor/product repo"
    size: 500
    source: "GitHub API via github_stargazer_scraper tool"
    filters:
      - has_email: true
      - has_company: true
      - title_contains: ["CTO", "Founder", "CEO", "VP Eng"]

  execution:
    tool: github_stargazer_scraper
    params:
      repo: "competitor/product"
      limit: 500
    schedule: "0 9 * * MON"  # Every Monday 9am
    timezone: "America/Los_Angeles"

  outreach:
    channel: email
    sender: "jake@company.com"
    subject: "Quick question about {{company}}"
    template: |
      Hi {{first_name}},

      Noticed you starred {{repo}} - looks like you're exploring dev tools.

      We built something similar but focused on {{value_prop}}.
      Would love to get your take on it.

      15 min this week?

      Jake

  metrics:
    - name: emails_sent
      type: counter
    - name: emails_opened
      type: counter
    - name: open_rate
      type: percentage
      formula: "emails_opened / emails_sent"
    - name: replies
      type: counter
    - name: response_rate
      type: percentage
      formula: "replies / emails_sent"
      success_threshold: 0.10
    - name: meetings_booked
      type: counter

  success_criteria:
    - response_rate > 0.10
    - meetings_booked >= 3

  failure_criteria:
    - response_rate < 0.02 after 100 sends
    - unsubscribe_rate > 0.05
    - bounce_rate > 0.10
```

---

## Tool Request Format

When FULLSEND needs a tool that doesn't exist:

```yaml
tool_request:
  id: req_20240115_001
  name: github_stargazer_scraper
  description: "Scrape users who starred a GitHub repo, extracting profile info"
  priority: high
  requested_by: fullsend
  experiment_blocked: exp_20240115_github_stars

  inputs:
    - name: repo
      type: string
      description: "owner/repo format"
      required: true
    - name: limit
      type: integer
      description: "Max users to return"
      default: 100

  outputs:
    - name: users
      type: list
      schema:
        username: string
        email: "string | null"
        name: "string | null"
        company: "string | null"
        bio: "string | null"
        location: "string | null"
        twitter: "string | null"

  requirements:
    - Must handle GitHub API rate limiting (5000 req/hr with token)
    - Must paginate correctly for repos with many stars
    - Must extract email from profile or commits if public
    - Return partial results on failure (don't lose progress)
    - Cache results to avoid re-scraping

  example_usage: |
    from tools.github_stargazer_scraper import scrape_stargazers

    users = scrape_stargazers(
        repo="anthropics/claude",
        limit=100
    )

    for user in users:
        if user.email and "CTO" in user.bio:
            send_email(user.email, template)
```

---

## Prompts

### prompts/system.txt

```
You are FULLSEND, the experiment designer for an autonomous GTM system.

## Your Role
You design experiments that test GTM hypotheses. You're creative, bold, and specific.
You don't just say "send emails" — you write the actual email template.
You don't just say "find leads" — you specify exactly where and how.

## Your Capabilities

1. **Design Experiments** — Complete specs with metrics, schedules, templates
2. **Use Existing Tools** — Check what's available, use them in your designs
3. **Request New Tools** — Write PRDs for Builder when you need something
4. **Run Simple Experiments** — You have Claude Code, you can execute directly
5. **Write Tactical Learnings** — Record what works at the execution level

## Available Tools
{{available_tools}}

## Recent Learnings
{{recent_learnings}}

## Design Principles

1. **Be Specific** — No placeholders. Write real templates.
2. **Be Bold** — Test interesting hypotheses, not safe ones.
3. **Be Measurable** — Every experiment has clear success/failure criteria.
4. **Be Iterative** — Design for learning, not just for wins.
5. **Be Efficient** — Use existing tools. Only request new ones when necessary.

## Output Format
Always output valid YAML that can be parsed programmatically.
Include experiment specs, tool requests, and any tactical learnings.
```

---

## Skills (Built-in Tools)

### skills/redis_tools.py
```python
def read_from_redis(key: str) -> Any:
    """Read a value from Redis."""

def write_to_redis(key: str, value: Any, ttl: int = None):
    """Write a value to Redis."""

def get_experiment(experiment_id: str) -> dict:
    """Get an experiment spec."""

def list_experiments(state: str = None) -> list[dict]:
    """List experiments, optionally filtered by state."""
```

### skills/file_tools.py
```python
def read_file(path: str) -> str:
    """Read a file from the filesystem."""

def write_file(path: str, content: str):
    """Write a file to the filesystem."""

def append_learning(learning: str):
    """Append a tactical learning to Redis."""
```

### skills/browserbase.py
```python
def research_company(domain: str) -> dict:
    """Research a company using Browserbase."""

def scrape_page(url: str) -> str:
    """Scrape a webpage and return text content."""
```

---

## Acceptance Criteria

- [ ] Connects to Redis on startup
- [ ] Subscribes to `fullsend:to_fullsend`
- [ ] Spawns Claude Code subprocess for experiment design
- [ ] Generates complete experiment specs in YAML
- [ ] Saves experiments to Redis (`experiments:{id}`)
- [ ] Saves metrics specs to Redis (`metrics_specs:{id}`)
- [ ] Publishes schedules for Executor
- [ ] Requests new tools from Builder when needed
- [ ] Notifies Orchestrator when experiments are ready
- [ ] Can run simple experiments directly
- [ ] Records tactical learnings to Redis
- [ ] Handles Claude Code timeout gracefully

---

## Test Plan

### Unit Tests
```bash
# Test YAML parsing
python -m services.fullsend.experiment --test-parse

# Test spawner
python -m services.fullsend.spawner --test "echo 'hello'"
```

### Integration Test
```bash
# Start FULLSEND
python -m services.fullsend.main &

# Send experiment request
redis-cli PUBLISH fullsend:to_fullsend '{
  "type": "experiment_request",
  "idea": "Scrape GitHub stargazers of anthropic/claude and email CTOs",
  "context": "We have had success with developer-focused outreach"
}'

# Check for experiment in Redis (within 60 seconds)
redis-cli HGETALL experiments:exp_*

# Check for tool request if needed
redis-cli SUBSCRIBE fullsend:builder_requests
```

### Experiment Quality Test
1. Send 3 different experiment ideas
2. Verify each generates complete spec with:
   - Specific target audience
   - Real email template (not placeholders)
   - Measurable metrics with thresholds
   - Clear success/failure criteria
   - Valid cron schedule

---

## Error Handling

```python
# Claude Code timeout
async def design_with_timeout(request):
    try:
        return await asyncio.wait_for(
            design_experiment(request),
            timeout=300  # 5 minutes max
        )
    except asyncio.TimeoutError:
        await publish("fullsend:to_orchestrator", {
            "type": "design_failed",
            "source": "fullsend",
            "reason": "Timeout - experiment too complex",
            "original_request": request
        })

# Invalid YAML output
def parse_experiment_yaml(output: str) -> dict:
    try:
        return yaml.safe_load(extract_yaml_block(output))
    except yaml.YAMLError as e:
        logger.error(f"Invalid YAML from Claude Code: {e}")
        raise ValueError("Claude Code produced invalid experiment spec")
```

---

## Dockerfile

```dockerfile
FROM python:3.11-slim

# Install Claude Code CLI
RUN curl -fsSL https://claude.ai/install.sh | sh

WORKDIR /app

COPY services/fullsend/requirements.txt .
RUN pip install -r requirements.txt

COPY services/fullsend/ ./services/fullsend/
COPY shared/ ./shared/
COPY tools/ ./tools/

# Mount points
VOLUME /app/tools
VOLUME /app/context

CMD ["python", "-m", "services.fullsend.main"]
```

---

## Notes for Builder

- **RALPH loops are the core pattern** — FULLSEND spawns Claude Code in loops
- TASKS.md = work to do, STATUS.md = memory between iterations
- For complex experiments: use RALPH (multi-step, reliable)
- For simple tasks: use direct spawn (single Claude Code call)
- YAML parsing must be robust (Claude might output extra text)
- Experiment IDs should be human-readable: `exp_20240115_github_stars`
- Always validate experiment specs before saving
- Tactical learnings go to Redis, not markdown files
- **Include actual email templates** — no placeholders!
- Claude Code can spawn MORE Claude Codes for subtasks (nested loops)
- Keep work_dir around for debugging failed experiments
