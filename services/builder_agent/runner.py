"""
Builder agent: consume everything that didn't work (fullsend.worker.results.failed),
summarize, classify build_tool vs human_todo. Uses Ralph loop to build (append tasks to RALPH/TASKS.md, run ralph.sh).
For human_todo items, publish to fullsend.human.todo. Not integrated into run_demo yet — run standalone to test.
"""

import json
import logging
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pika
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage

from services.orchestrator.llm import get_orchestrator_llm

_project_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(_project_root / ".env")

logger = logging.getLogger(__name__)

DEFAULT_RABBITMQ_URL = "amqp://localhost:5672/"
DEFAULT_FAILED_QUEUE = "fullsend.worker.results.failed"
DEFAULT_HUMAN_TODO_QUEUE = "fullsend.human.todo"
RALPH_TASKS_PATH = _project_root / "RALPH" / "TASKS.md"
RALPH_SCRIPT_PATH = _project_root / "RALPH" / "ralph.sh"
RALPH_BUILDER_OUTPUT = _project_root / "RALPH" / "builder_output"
REGISTER_RALPH_SCRIPT = _project_root / "scripts" / "register_ralph_tools.py"


def _slug(name: str) -> str:
    """Turn a name into a slug (e.g. 'HubSpot Sync' -> hubspot-sync)."""
    s = re.sub(r"[^a-zA-Z0-9\s]", "", (name or "").strip().lower())
    return "-".join(s.split())[:40] or "tool"


def _format_failures_for_llm(failures: list[dict]) -> str:
    """Format failed step messages for the LLM."""
    lines = []
    for i, f in enumerate(failures, 1):
        task = (f.get("task") or "")[:120]
        step = (f.get("step") or "")[:120]
        err = (f.get("error_preview") or f.get("result") or "")[:200]
        lines.append(f"{i}. Task: {task}\n   Step: {step}\n   Error: {err}")
    return "\n\n".join(lines)


def _parse_llm_plan(response: str) -> dict:
    """Parse LLM JSON plan (summary + items with action, tool_*, human_*). Tolerate markdown code fence."""
    text = (response or "").strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    else:
        # Try to find first { ... }
        m2 = re.search(r"\{.*\}", text, re.DOTALL)
        if m2:
            text = m2.group(0)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("LLM plan JSON parse failed; returning empty plan")
        return {"summary": "", "items": []}


def _summarize_and_plan(failures: list[dict], llm) -> dict:
    """Use LLM to summarize failures and plan: for each item, build_tool (with tool_name, description, constraint) or human_todo (human_task, human_reason)."""
    blob = _format_failures_for_llm(failures)
    system = """You are a builder agent. You receive a list of executor step failures (what didn't work).
For each failure, decide:
- build_tool: we can add a practical tool/skill (e.g. a script, API wrapper, or automation) so this can succeed next time.
- human_todo: this needs a human (e.g. API keys, legal approval, custom code we can't generate, or unclear requirement).

Output only valid JSON (no markdown, no explanation) with this exact shape:
{
  "summary": "2-4 sentence summary of what didn't work and why.",
  "items": [
    {
      "step_preview": "short step description",
      "error_preview": "short error",
      "action": "build_tool" or "human_todo",
      "tool_name": "slug-name (only if build_tool)",
      "tool_description": "one sentence (only if build_tool)",
      "tool_constraint": "one sentence constraint (only if build_tool)",
      "human_task": "what human should do (only if human_todo)",
      "human_reason": "why builder can't do it (only if human_todo)"
    }
  ]
}
Every item must have action, step_preview, error_preview. For build_tool add tool_name, tool_description, tool_constraint. For human_todo add human_task, human_reason."""

    user = f"""FAILED EXECUTOR STEPS:

{blob}

Output the JSON plan (summary + items with action build_tool or human_todo and the required fields for each)."""

    try:
        resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        raw = resp.content if hasattr(resp, "content") else str(resp)
        return _parse_llm_plan(raw)
    except Exception as e:
        logger.exception("LLM summarize_and_plan failed: %s", e)
        return {"summary": "", "items": []}


def _next_ralph_task_id() -> int:
    """Parse RALPH/TASKS.md for existing TASK-NNN, return next id (1-based)."""
    if not RALPH_TASKS_PATH.exists():
        return 1
    text = RALPH_TASKS_PATH.read_text(encoding="utf-8")
    ids = [int(m) for m in re.findall(r"TASK-(\d+)", text)]
    return max(ids, default=0) + 1


def _append_ralph_build_tasks(build_tool_items: list[dict]) -> list[str]:
    """
    Append builder-driven tasks to RALPH/TASKS.md. Each task tells Ralph to create
    RALPH/builder_output/tool_<slug>.json and run scripts/register_ralph_tools.py.
    Returns list of tool slugs added.
    """
    if not build_tool_items:
        return []
    RALPH_BUILDER_OUTPUT.mkdir(parents=True, exist_ok=True)
    next_id = _next_ralph_task_id()
    lines = []
    if not RALPH_TASKS_PATH.exists():
        lines.append("# RALPH Tasks\n\n")
    # Check if builder section exists
    text = RALPH_TASKS_PATH.read_text(encoding="utf-8") if RALPH_TASKS_PATH.exists() else ""
    if "## Builder-driven tasks" not in text:
        lines.append("\n## Builder-driven tasks (from executor failures)\n\n")
    slugs: list[str] = []
    for item in build_tool_items:
        tool_name = _slug(item.get("tool_name") or item.get("step_preview") or "tool")
        tool_description = (item.get("tool_description") or "").strip() or f"Tool for: {(item.get('step_preview') or '')[:80]}"
        tool_constraint = (item.get("tool_constraint") or "").strip() or "Use when executor step failed for this kind of task."
        step_preview = (item.get("step_preview") or "")[:100]
        error_preview = (item.get("error_preview") or "")[:100]
        task_id = f"TASK-{next_id:03d}"
        next_id += 1
        task_line = (
            f"- [ ] {task_id}: Add tool **{tool_name}**: {tool_description}\n"
            f"  - Constraint: {tool_constraint}\n"
            f"  - From executor failure: step \"{step_preview}\", error \"{error_preview}\"\n"
            f"  - Create RALPH/builder_output/tool_{tool_name}.json with keys: name, description, constraints, skill_content (markdown string), addresses_blocked (list of {{task, reason}}).\n"
            f"  - Run from repo root: python scripts/register_ralph_tools.py\n"
            f"  - Update RALPH/STATUS.md with what you did. Mark task done in TASKS.md. Output **TASK_DONE**\n\n"
        )
        lines.append(task_line)
        slugs.append(tool_name)
    with open(RALPH_TASKS_PATH, "a", encoding="utf-8") as f:
        f.writelines(lines)
    logger.info("Appended %d Ralph task(s) to RALPH/TASKS.md: %s", len(slugs), slugs)
    return slugs


def _run_ralph_loop(timeout_seconds: int = 600) -> bool:
    """Run RALPH/ralph.sh from repo root. Returns True if exit 0."""
    if not RALPH_SCRIPT_PATH.exists():
        logger.warning("RALPH/ralph.sh not found; skipping Ralph loop")
        return False
    try:
        env = os.environ.copy()
        result = subprocess.run(
            [str(RALPH_SCRIPT_PATH)],
            cwd=str(_project_root),
            env=env,
            timeout=timeout_seconds,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning("Ralph loop exited %s: %s", result.returncode, (result.stderr or result.stdout or "")[:500])
            return False
        logger.info("Ralph loop completed successfully")
        return True
    except subprocess.TimeoutExpired:
        logger.warning("Ralph loop timed out after %s s", timeout_seconds)
        return False
    except Exception as e:
        logger.exception("Ralph loop failed: %s", e)
        return False


def _run_register_ralph_tools() -> list[str]:
    """Run scripts/register_ralph_tools.py; return list of registered tool names (from stdout/log)."""
    if not REGISTER_RALPH_SCRIPT.exists():
        return []
    try:
        result = subprocess.run(
            [os.executable, str(REGISTER_RALPH_SCRIPT)],
            cwd=str(_project_root),
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            logger.warning("register_ralph_tools failed: %s", (result.stderr or result.stdout or "")[:300])
            return []
        # Parse "Registered N tool(s): a, b, c" or "Registered tool/skill: X"
        out = (result.stdout or "") + (result.stderr or "")
        slugs = []
        for m in re.findall(r"Registered tool/skill:\s*(\S+)", out):
            slugs.append(m.strip())
        return slugs
    except Exception as e:
        logger.warning("register_ralph_tools failed: %s", e)
        return []


def _publish_human_todo(channel, queue: str, task: str, reason: str, context: str) -> None:
    """Publish one human-to-do message to RabbitMQ."""
    msg = {
        "task": (task or "").strip(),
        "reason": (reason or "").strip(),
        "context": (context or "").strip()[:500],
        "source": "builder_agent",
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    channel.basic_publish(
        exchange="",
        routing_key=queue,
        body=json.dumps(msg).encode("utf-8"),
        properties=pika.BasicProperties(delivery_mode=2),
    )
    logger.info("Published human todo: %s", (task or "")[:60])


def run_builder_agent(
    rabbitmq_url: str | None = None,
    failed_queue: str | None = None,
    human_todo_queue: str | None = None,
    max_messages: int | None = None,
    redis_url: str | None = None,
) -> tuple[int, int, list[str], list[dict]]:
    """
    Consume from fullsend.worker.results.failed, summarize with LLM, classify build_tool vs human_todo,
    build practical tools (Redis), publish human todos (RabbitMQ).
    Returns (built_count, human_todo_count, built_slugs, human_todo_items).
    Not integrated into run_demo — run standalone to test.
    """
    url = rabbitmq_url or os.getenv("RABBITMQ_URL", DEFAULT_RABBITMQ_URL)
    fq = failed_queue or os.getenv("WORKER_RESULTS_FAILED_QUEUE", DEFAULT_FAILED_QUEUE)
    hq = human_todo_queue or os.getenv("HUMAN_TODO_QUEUE", DEFAULT_HUMAN_TODO_QUEUE)

    params = pika.URLParameters(url)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
    channel.queue_declare(queue=fq, durable=True)
    channel.queue_declare(queue=hq, durable=True)

    # Drain failed queue (up to max_messages)
    failures: list[dict] = []
    while True:
        if max_messages is not None and len(failures) >= max_messages:
            break
        method, _, body = channel.basic_get(queue=fq, auto_ack=False)
        if method is None:
            break
        try:
            payload = json.loads(body.decode("utf-8"))
            failures.append(payload)
            channel.basic_ack(method.delivery_tag)
        except Exception as e:
            logger.exception("Failed to parse failed message: %s", e)
            channel.basic_nack(method.delivery_tag, requeue=False)

    connection.close()

    if not failures:
        logger.info("Builder agent: no failed messages to process")
        return 0, 0, [], []

    logger.info("Builder agent: processing %d failure(s)", len(failures))

    # Summarize and plan (LLM)
    llm = get_orchestrator_llm()
    plan = _summarize_and_plan(failures, llm)
    summary = plan.get("summary") or ""
    items = plan.get("items") or []
    if summary:
        logger.info("Summary: %s", summary[:200])

    build_tool_items = [i for i in items if (i.get("action") or "").strip().lower() == "build_tool"]
    human_todo_items_list = [i for i in items if (i.get("action") or "").strip().lower() == "human_todo"]

    # Ralph loop: append build_tool tasks to RALPH/TASKS.md, run ralph.sh, then register any JSONs Ralph created
    built_slugs: list[str] = []
    if build_tool_items:
        built_slugs = _append_ralph_build_tasks(build_tool_items)
        _run_ralph_loop(timeout_seconds=600)
        registered = _run_register_ralph_tools()
        if registered:
            built_slugs = registered
    built_count = len(built_slugs)

    # Publish human_todo items to RabbitMQ
    connection2 = pika.BlockingConnection(pika.URLParameters(url))
    channel2 = connection2.channel()
    channel2.queue_declare(queue=hq, durable=True)
    human_todo_count = 0
    human_todo_items: list[dict] = []
    for item in human_todo_items_list:
        step_preview = (item.get("step_preview") or "").strip()
        error_preview = (item.get("error_preview") or "").strip()
        human_task = (item.get("human_task") or step_preview or "Review failed step").strip()
        human_reason = (item.get("human_reason") or error_preview or "Builder could not automate.").strip()
        try:
            _publish_human_todo(channel2, hq, human_task, human_reason, step_preview + "\n" + error_preview)
            human_todo_count += 1
            human_todo_items.append({"task": human_task, "reason": human_reason, "context": step_preview})
            logger.info("Published human todo: %s", human_task[:60])
        except Exception as e:
            logger.warning("Failed to publish human todo: %s", e)
    connection2.close()

    logger.info("Builder agent done: Ralph built %d tool(s) %s, human todo %d", built_count, built_slugs, human_todo_count)
    return built_count, human_todo_count, built_slugs, human_todo_items


def seed_failed_queue(
    count: int = 3,
    rabbitmq_url: str | None = None,
    failed_queue: str | None = None,
) -> int:
    """
    Publish a few test messages to fullsend.worker.results.failed so the builder agent has something to consume.
    Returns number of messages published.
    """
    url = rabbitmq_url or os.getenv("RABBITMQ_URL", DEFAULT_RABBITMQ_URL)
    fq = failed_queue or os.getenv("WORKER_RESULTS_FAILED_QUEUE", DEFAULT_FAILED_QUEUE)
    now = datetime.now(tz=timezone.utc).isoformat()
    test_failures = [
        {
            "task_id": "test-task-001",
            "task": "Build a Python script that parses HTML and extracts headings and links",
            "topic": "ICP campaign: content extraction",
            "order": 1,
            "step_index": 1,
            "step": "Run a Python script to fetch a page, parse HTML, and return headings and links as JSON",
            "result": "Executor: No Python script runner tool; step requires a small script",
            "error_preview": "Executor: No Python script runner tool; step requires a small script",
            "source": "executor",
            "created_at": now,
        },
        {
            "task_id": "test-task-002",
            "task": "Build a simple web scraper for product listings",
            "topic": "ICP campaign: competitor scraping",
            "order": 2,
            "step_index": 1,
            "step": "Scrape the product list from a given URL and return title, price, and link for each item",
            "result": "Executor: Scraper tool not available; need a reusable scraper for list pages",
            "error_preview": "Executor: Scraper tool not available; need a reusable scraper for list pages",
            "source": "executor",
            "created_at": now,
        },
        {
            "task_id": "test-task-003",
            "task": "Use Browserbase to capture a page screenshot and extract the main heading",
            "topic": "ICP campaign: browser-based checks",
            "order": 3,
            "step_index": 1,
            "step": "Open URL in Browserbase, take a screenshot, extract the main h1 text, and return it",
            "result": "Executor: Browserbase session failed or navigate + extract tool not configured",
            "error_preview": "Executor: Browserbase session failed or navigate + extract tool not configured",
            "source": "executor",
            "created_at": now,
        },
    ]
    to_publish = test_failures[:count]
    params = pika.URLParameters(url)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
    channel.queue_declare(queue=fq, durable=True)
    for msg in to_publish:
        channel.basic_publish(
            exchange="",
            routing_key=fq,
            body=json.dumps(msg).encode("utf-8"),
            properties=pika.BasicProperties(delivery_mode=2),
        )
    connection.close()
    logger.info("Seeded %d test message(s) to %s", len(to_publish), fq)
    return len(to_publish)
