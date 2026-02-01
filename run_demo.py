#!/usr/bin/env python3
"""
Self-improving agent demo: one script runs the full loop for 2 cycles.

  1. Consumer posts a query (topic) -> roundtable publishes GTM tasks to orchestrator queue.
  2. Orchestrator plans, runs what it can (writes steps to queue), writes task state + blocked to Redis.
  3. Analyzer runs: reads blocked from Redis, roundtable (builder mode), publishes to builder queue.
  4. Builder stub consumes builder queue, adds minimal tools/skills to Redis.
  5. Requeue: same GTM task payloads that had blocked -> back to orchestrator queue.
  6. Orchestrator runs again (cycle 2) with expanded tools -> fewer/no blocked.

Usage: python run_demo.py "Topic: Your campaign idea"
Requires: REDIS_URL, RABBITMQ_URL, WANDB_KEY (or OPENAI_API_KEY) in .env
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Log file next to this script (project root when run from GTM_agent_auto_mode_on)
DEMO_LOG_PATH = Path(__file__).resolve().parent / "Demo_logs.txt"
DEMO_VERSION = "1.0"

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def _demo_log(event: str, **kwargs) -> None:
    """Append one JSON line to Demo_logs.txt (event + ts + kwargs)."""
    payload = {"event": event, "ts": datetime.now(timezone.utc).isoformat(), **kwargs}
    with open(DEMO_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _timed_agent(agent: str, fn, *args, **kwargs):
    """Run fn, log agent_run with duration_sec, return fn result."""
    t0 = time.perf_counter()
    try:
        return fn(*args, **kwargs)
    finally:
        duration_sec = round(time.perf_counter() - t0, 2)
        _demo_log("agent_run", agent=agent, duration_sec=duration_sec)


def _finish_wandb_run(
    blocked_before_count: int,
    blocked_after_count: int,
    tasks_published: int = 0,
    tools_added: int = 0,
    requeued: int = 0,
) -> None:
    """If a W&B run is active, update summary, log wandb_run to demo log, and finish."""
    try:
        import wandb
        if wandb.run is None:
            return
        wandb.run.summary.update(
            blocked_before_count=blocked_before_count,
            blocked_after_count=blocked_after_count,
            tasks_published=tasks_published,
            tools_added=tools_added,
            requeued=requeued,
        )
        run_id = getattr(wandb.run, "id", None) or ""
        run_url = getattr(wandb.run, "url", None) or ""
        if run_id:
            _demo_log("wandb_run", run_id=run_id, run_url=run_url)
        wandb.finish()
    except Exception as e:
        logger.warning("W&B finish failed: %s", e)


def _report_failed_tasks(label: str, tasks: list[dict]) -> None:
    """Print failed/blocked tasks report."""
    print(f"\n--- Failed/blocked tasks {label} ---")
    if not tasks:
        print("  (none)")
        return
    total_blocked = sum(len(t.get("blocked") or []) for t in tasks)
    print(f"  {len(tasks)} task(s) with blocked items ({total_blocked} blocked item(s) total)")
    for t in tasks[:5]:
        ctx = (t.get("context") or "")[:60]
        n = len(t.get("blocked") or [])
        print(f"    - {n} blocked: {ctx}...")
    if len(tasks) > 5:
        print(f"    ... and {len(tasks) - 5} more")


def _blocked_snapshot(tasks: list[dict]) -> str:
    """Flatten blocked items from task states into a single text snapshot (task + reason per line)."""
    lines = []
    for t in tasks:
        ctx = (t.get("context") or "")[:120]
        for b in t.get("blocked") or []:
            task_desc = (b.get("task") or "").strip()
            reason = (b.get("reason") or "").strip()
            lines.append(f"- GTM task: {ctx}... | Blocked: {task_desc} | Reason: {reason}")
    return "\n".join(lines) if lines else "(none)"


def _llm_before_after_report(
    blocked_before: list[dict],
    blocked_after: list[dict],
    builder_added: list[str],
) -> str:
    """
    Use the orchestrator LLM to compare before/after blocked snapshots and report
    what problems the builder solved in particular and which remain.
    """
    from services.orchestrator.llm import get_orchestrator_llm
    from langchain_core.messages import HumanMessage, SystemMessage

    before_text = _blocked_snapshot(blocked_before)
    after_text = _blocked_snapshot(blocked_after)
    tools_added = ", ".join(builder_added) if builder_added else "(none)"

    system = """You are an analyst for a self-improving agent demo. You will see:
1) Blocked items BEFORE the builder ran (GTM tasks that could not be executed; each has a "Blocked" step and "Reason").
2) Blocked items AFTER the builder ran and the orchestrator re-planned with new tools.
3) The list of tools/skills the builder added (stub names).

Your job: Write a short report (bullet points, 1–2 paragraphs max) that:
- States which problems the builder SOLVED in particular (blocked items that appeared before and are gone or reduced after, or that the new tools directly address).
- States which problems REMAIN (blocked items that still appear after, or new ones).
- Explains why the before/after counts might differ (e.g. re-planning created new task states, or time limits meant only some tasks were re-processed).
Do not repeat raw lists; synthesize."""

    user = f"""BLOCKED ITEMS BEFORE BUILDER:
{before_text}

BLOCKED ITEMS AFTER BUILDER (re-plan with new tools):
{after_text}

TOOLS/SKILLS THE BUILDER ADDED: {tools_added}

Write your analyst report (what the builder solved, what remains, and why counts may differ)."""

    try:
        llm = get_orchestrator_llm()
        response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        return (response.content if hasattr(response, "content") else str(response)).strip()
    except Exception as e:
        return f"(LLM report failed: {e})"


def main() -> None:
    topic = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else None
    if not topic:
        print('Usage: python run_demo.py "Topic: Your campaign idea"', file=sys.stderr)
        sys.exit(1)

    # Fresh log for this run
    DEMO_LOG_PATH.write_text("", encoding="utf-8")
    _demo_log("demo_start", topic=topic)

    # Optional: push this demo run to W&B
    wandb_run_started = False
    if os.getenv("WANDB_PROJECT") and (os.getenv("WANDB_API_KEY") or os.getenv("WANDB_KEY")):
        try:
            import wandb
            wandb.init(
                project=os.getenv("WANDB_PROJECT"),
                entity=os.getenv("WANDB_ENTITY") or None,
                config={"topic": topic, "demo_version": DEMO_VERSION},
                name=f"demo-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
            )
            wandb_run_started = wandb.run is not None
        except Exception as e:
            logger.warning("W&B init failed: %s", e)

    from services.roundtable.runner import run_roundtable, _parse_summary_into_tasks
    from services.orchestrator.runner import run_orchestrator_daemon
    from services.analyzer.runner import run_analyzer
    from services.builder_stub import run_builder_stub
    from services.requeue_blocked import requeue_blocked_tasks, get_task_states_with_blocked

    # --- Cycle 1: plan and run what we can ---
    logger.info("=== Demo cycle 1: roundtable -> orchestrator -> steps queue + Redis ===")
    result = _timed_agent(
        "roundtable",
        run_roundtable,
        topic=topic,
        publish_to="orchestrator",
        max_rounds=2,
    )
    summary = result["summary"]
    tasks_roundtable = _parse_summary_into_tasks(summary)
    M = len(tasks_roundtable)
    logger.info("Roundtable published %d GTM task(s) to orchestrator queue", M)
    _demo_log("roundtable_done", tasks_published=M, summary_preview=(summary or "")[:80])
    if M == 0:
        logger.warning("No tasks to process; exiting")
        _demo_log("demo_end", blocked_before_count=0, blocked_after_count=0)
        if wandb_run_started:
            _finish_wandb_run(0, 0, tasks_published=0, tools_added=0, requeued=0)
        return

    _timed_agent("orchestrator", run_orchestrator_daemon, max_messages=M, time_limit_seconds=5.0)
    _demo_log("orchestrator_cycle_1_done", max_messages=M, time_limit_sec=5.0)
    blocked_before_analyzer = get_task_states_with_blocked()
    blocked_item_count_before = sum(len(t.get("blocked") or []) for t in blocked_before_analyzer)
    _demo_log("blocked_before", task_count=len(blocked_before_analyzer), blocked_item_count=blocked_item_count_before)
    _report_failed_tasks("BEFORE analyzer", blocked_before_analyzer)

    # --- Analyzer -> builder queue ---
    logger.info("=== Analyzer: builder roundtable -> builder queue ===")
    _timed_agent("analyzer", run_analyzer)
    _demo_log("analyzer_done")

    # --- Builder stub: add tools/skills to Redis ---
    logger.info("=== Builder stub: consume builder queue, add tools/skills to Redis ===")
    _builder_count, builder_added = _timed_agent("builder", run_builder_stub)
    _demo_log("builder_stub_done", added_count=_builder_count, added_slugs=builder_added)

    # --- Requeue blocked task payloads ---
    requeued = requeue_blocked_tasks()
    _demo_log("requeue_done", requeued=requeued)
    if requeued == 0:
        logger.info("Nothing to requeue; demo ends after analyzer")
        blocked_after_analyzer = get_task_states_with_blocked()
        blocked_item_count_after = sum(len(t.get("blocked") or []) for t in blocked_after_analyzer)
        _demo_log("blocked_after", task_count=len(blocked_after_analyzer), blocked_item_count=blocked_item_count_after)
        _report_failed_tasks("AFTER analyzer (no cycle 2)", blocked_after_analyzer)
        print("\n--- Analyst report (before vs after) ---")
        report = _llm_before_after_report(blocked_before_analyzer, blocked_after_analyzer, builder_added)
        print(report)
        _demo_log("analyst_report", report=report, report_preview=report[:200] if len(report) > 200 else report)
        _demo_log("demo_end", blocked_before_count=len(blocked_before_analyzer), blocked_after_count=len(blocked_after_analyzer))
        if wandb_run_started:
            _finish_wandb_run(
                len(blocked_before_analyzer), len(blocked_after_analyzer),
                tasks_published=M, tools_added=len(builder_added), requeued=0,
            )
        return

    # --- Cycle 2: re-plan with new tools ---
    logger.info("=== Demo cycle 2: orchestrator re-plans requeued tasks with new tools ===")
    _timed_agent("orchestrator", run_orchestrator_daemon, max_messages=requeued, time_limit_seconds=5.0)
    _demo_log("orchestrator_cycle_2_done", max_messages=requeued, time_limit_sec=5.0)
    blocked_after_analyzer = get_task_states_with_blocked()
    blocked_item_count_after = sum(len(t.get("blocked") or []) for t in blocked_after_analyzer)
    _demo_log("blocked_after", task_count=len(blocked_after_analyzer), blocked_item_count=blocked_item_count_after)
    _report_failed_tasks("AFTER analyzer (cycle 2)", blocked_after_analyzer)

    # --- LLM analyst report: what did the builder solve? ---
    print("\n--- Analyst report: what the builder solved ---")
    report = _llm_before_after_report(blocked_before_analyzer, blocked_after_analyzer, builder_added)
    print(report)
    _demo_log("analyst_report", report=report, report_preview=report[:200] if len(report) > 200 else report)
    _demo_log("demo_end", blocked_before_count=len(blocked_before_analyzer), blocked_after_count=len(blocked_after_analyzer))
    if wandb_run_started:
        _finish_wandb_run(
            len(blocked_before_analyzer), len(blocked_after_analyzer),
            tasks_published=M, tools_added=len(builder_added), requeued=requeued,
        )

    # --- Summary ---
    print("\n--- Demo summary ---")
    print(f"Failed/blocked tasks BEFORE analyzer: {len(blocked_before_analyzer)} task(s)")
    print(f"Builder added: {builder_added}")
    print(f"Requeued: {requeued} task(s)")
    print(f"Failed/blocked tasks AFTER analyzer: {len(blocked_after_analyzer)} task(s)")
    print("(Orchestrator runs with 5s time limit; analyst report explains before/after.)")


if __name__ == "__main__":
    main()
