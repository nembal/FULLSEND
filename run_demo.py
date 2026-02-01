#!/usr/bin/env python3
"""
Self-improving agent demo: one script runs the full loop for 2 cycles (end-to-end ICP campaign).

  1. Roundtable: topic (e.g. ICP campaign) -> publishes GTM tasks to orchestrator queue.
  2. Orchestrator: plans steps, publishes to worker steps queue, writes task state + blocked to Redis.
  3. Executor: consumes worker steps, runs each step (Claude Code + Browserbase), loads skills from Redis,
     updates task state, publishes what worked / what didn't to result queues.
  4. Analyzer: reads blocked from Redis, roundtable (builder mode), publishes to builder queue.
  5. Builder agent: consumes failed queue, summarizes, builds tools (Ralph), publishes human_todo.
  6. Requeue: same GTM task payloads that had blocked -> back to orchestrator queue.
  7. Orchestrator runs again (cycle 2) with expanded tools -> fewer/no blocked.
  8. (Optional) Executor runs again for cycle 2 steps.

Usage: python run_demo.py "Topic: ICP campaign for SMB SaaS founders"
Requires: REDIS_URL, RABBITMQ_URL, ANTHROPIC_API_KEY (executor), WANDB_KEY or OPENAI_API_KEY (roundtable/orchestrator) in .env
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


def _format_report_for_terminal(report: str) -> str:
    """Format markdown report for terminal: section headers and bullets stand out."""
    import re
    text = report.strip()
    # ## Campaign Summary -> \n--- Campaign Summary ---\n
    text = re.sub(r"^##\s+(.+)$", r"\n--- \1 ---\n", text, flags=re.MULTILINE)
    # **foo** -> foo (terminal doesn't render bold; optional: keep as-is)
    # Leave ** for now so it's visible; strip if you prefer
    return text.strip()


def _format_campaign_tasks(all_task_states: list[dict] | None) -> str:
    """Format all task states for the report prompt: GTM task, planned steps, blocked. Truncate to avoid token overflow."""
    if not all_task_states:
        return "(no orchestrator task states found)"
    lines = []
    ctx_max = 200
    steps_max = 10
    for t in all_task_states:
        ctx = (t.get("context") or "").strip()
        if len(ctx) > ctx_max:
            ctx = ctx[:ctx_max] + "..."
        next_steps = t.get("next_steps") or []
        steps_str = "\n    ".join(f"- {s}" for s in (next_steps[:steps_max] if next_steps else []))
        if len(next_steps) > steps_max:
            steps_str += f"\n    ... and {len(next_steps) - steps_max} more"
        blocked = t.get("blocked") or []
        blocked_str = "; ".join(
            f"{b.get('task', '')} ({b.get('reason', '')})" for b in blocked[:5]
        ) if blocked else "(none)"
        if len(blocked) > 5:
            blocked_str += f" ... and {len(blocked) - 5} more"
        lines.append(
            f"GTM task: {ctx}\n  Steps for executor (Claude Code + Browserbase):\n    {steps_str or '(none)'}\n  Could not execute (blocked): {blocked_str}"
        )
    return "\n\n".join(lines)


def _llm_before_after_report(
    blocked_before: list[dict],
    blocked_after: list[dict],
    builder_added: list[str],
    roundtable_summary: str = "",
    all_task_states: list[dict] | None = None,
) -> str:
    """
    Use the orchestrator LLM to summarize the campaign (all tasks carried out) and compare
    before/after blocked snapshots, reporting what the builder solved and what remains.
    """
    from services.orchestrator.llm import get_orchestrator_llm
    from langchain_core.messages import HumanMessage, SystemMessage

    before_text = _blocked_snapshot(blocked_before)
    after_text = _blocked_snapshot(blocked_after)
    tools_added = ", ".join(builder_added) if builder_added else "(none)"
    campaign_tasks_text = _format_campaign_tasks(all_task_states)
    roundtable_section = (roundtable_summary or "").strip() or "(no roundtable summary)"

    system = """You are an analyst for a self-improving agent demo. Context:
- The EXECUTOR is a Claude Code instance with Browserbase (browser automation). It runs the implementation steps the orchestrator plans.
- The BUILDER is a Ralph loop on Claude Code. It adds tools/skills when the executor cannot run steps (e.g. missing integrations).

You will see:
1) The campaign/roundtable summary (GTM tasks from the roundtable).
2) All GTM tasks: for each, the steps planned for the executor (Claude Code + Browserbase) and what could not be executed (blocked).
3) Blocked items BEFORE the builder ran (steps the executor could not run).
4) Blocked items AFTER the builder (Ralph loop) ran and the orchestrator re-planned with new tools.
5) The tools/skills the builder (Ralph loop on Claude Code) added.

Your job: Write a report in strict markdown format so it displays well in terminal and dashboard.

Use exactly this structure (copy the headers; fill in the content):

## Campaign Summary
(One short paragraph: what GTM tasks were planned, what steps the executor Claude Code + Browserbase was asked to run, what ran, and what was blocked.)

## Analyst Report
(Use bullet points.)
- **What the builder solved:** (which blocked items are gone or reduced; which new tools addressed them)
- **What remains:** (still blocked or new problems)
- **Why counts differ:** (re-planning, time limits, etc.)

Keep paragraphs and bullets concise. Do not repeat raw lists; synthesize."""

    user = f"""CAMPAIGN / ROUNDTABLE SUMMARY:
{roundtable_section}

ALL TASKS (GTM task, steps for executor Claude Code + Browserbase, could not execute):
{campaign_tasks_text}

BLOCKED ITEMS BEFORE BUILDER (Ralph loop):
{before_text}

BLOCKED ITEMS AFTER BUILDER (Ralph loop) and re-plan:
{after_text}

TOOLS/SKILLS THE BUILDER (Ralph loop on Claude Code) ADDED: {tools_added}

Output the report using the exact markdown structure above (## Campaign Summary, then ## Analyst Report with bullets)."""

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
        print('Example (ICP campaign): python run_demo.py "Topic: ICP campaign for SMB SaaS founders"', file=sys.stderr)
        sys.exit(1)

    # Fresh log for this run
    DEMO_LOG_PATH.write_text("", encoding="utf-8")
    _demo_log("demo_start", topic=topic)

    # Clear Redis and RabbitMQ for a fresh start
    from services.clear_demo_state import clear_redis_and_queues
    redis_deleted, queues_purged = clear_redis_and_queues()
    logger.info("Fresh start: Redis %d key(s) deleted, %d queue(s) purged", redis_deleted, queues_purged)
    _demo_log("demo_clear", redis_deleted=redis_deleted, queues_purged=queues_purged)

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
    from services.executor.worker import run_executor_daemon as run_executor_daemon_impl
    from services.analyzer.runner import run_analyzer
    from services.builder_agent.runner import run_builder_agent
    from services.requeue_blocked import requeue_blocked_tasks, get_task_states_with_blocked, get_all_task_states

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

    # --- Executor: consume worker steps, run each (Claude Code + Browserbase), skills from Redis, result queues ---
    all_states_cycle1 = get_all_task_states()
    step_count = sum(len(s.get("next_steps") or []) for s in all_states_cycle1)
    if step_count > 0:
        logger.info("=== Executor: run %d step(s) (Claude Code + Browserbase, skills from Redis) ===", step_count)
        _timed_agent(
            "executor",
            run_executor_daemon_impl,
            max_messages=step_count,
            time_limit_seconds=min(300, 60 + step_count * 30),
        )
        _demo_log("executor_cycle_1_done", max_messages=step_count)
    else:
        logger.info("=== Executor: no steps to run (all blocked or no tasks) ===")

    blocked_before_analyzer = get_task_states_with_blocked()
    blocked_item_count_before = sum(len(t.get("blocked") or []) for t in blocked_before_analyzer)
    _demo_log("blocked_before", task_count=len(blocked_before_analyzer), blocked_item_count=blocked_item_count_before)
    _report_failed_tasks("BEFORE analyzer", blocked_before_analyzer)

    # --- Analyzer -> builder queue ---
    logger.info("=== Analyzer: builder roundtable -> builder queue ===")
    _timed_agent("analyzer", run_analyzer)
    _demo_log("analyzer_done")

    # --- Builder agent: consume failed queue, Ralph build, human_todo ---
    logger.info("=== Builder agent: consume failed queue, build tools (Ralph), human_todo ===")
    built_count, human_todo_count, builder_added, _human_items = _timed_agent("builder", run_builder_agent)
    _demo_log("builder_agent_done", built_count=built_count, built_slugs=builder_added, human_todo_count=human_todo_count)

    # --- Snapshot all task states before requeue (requeue deletes requeued task states) ---
    all_task_states_after_cycle1 = get_all_task_states()

    # --- Requeue blocked task payloads ---
    requeued = requeue_blocked_tasks()
    _demo_log("requeue_done", requeued=requeued)
    if requeued == 0:
        logger.info("Nothing to requeue; demo ends after analyzer")
        blocked_after_analyzer = get_task_states_with_blocked()
        blocked_item_count_after = sum(len(t.get("blocked") or []) for t in blocked_after_analyzer)
        _demo_log("blocked_after", task_count=len(blocked_after_analyzer), blocked_item_count=blocked_item_count_after)
        _report_failed_tasks("AFTER analyzer (no cycle 2)", blocked_after_analyzer)
        print("\n" + "=" * 60)
        print("REPORT")
        print("=" * 60)
        report = _llm_before_after_report(
            blocked_before_analyzer, blocked_after_analyzer, builder_added,
            roundtable_summary=summary, all_task_states=all_task_states_after_cycle1,
        )
        print(_format_report_for_terminal(report))
        print("=" * 60)
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

    # --- Executor cycle 2: run steps from re-planned tasks ---
    all_states_cycle2 = get_all_task_states()
    step_count_2 = sum(len(s.get("next_steps") or []) for s in all_states_cycle2)
    if step_count_2 > 0:
        logger.info("=== Executor cycle 2: run %d step(s) ===", step_count_2)
        _timed_agent(
            "executor",
            run_executor_daemon_impl,
            max_messages=step_count_2,
            time_limit_seconds=min(300, 60 + step_count_2 * 30),
        )
        _demo_log("executor_cycle_2_done", max_messages=step_count_2)

    blocked_after_analyzer = get_task_states_with_blocked()
    blocked_item_count_after = sum(len(t.get("blocked") or []) for t in blocked_after_analyzer)
    _demo_log("blocked_after", task_count=len(blocked_after_analyzer), blocked_item_count=blocked_item_count_after)
    _report_failed_tasks("AFTER analyzer (cycle 2)", blocked_after_analyzer)

    # --- LLM analyst report: what did the builder solve? ---
    print("\n" + "=" * 60)
    print("REPORT")
    print("=" * 60)
    report = _llm_before_after_report(
        blocked_before_analyzer, blocked_after_analyzer, builder_added,
        roundtable_summary=summary, all_task_states=all_task_states_after_cycle1,
    )
    print(_format_report_for_terminal(report))
    print("=" * 60)
    _demo_log("analyst_report", report=report, report_preview=report[:200] if len(report) > 200 else report)
    _demo_log("demo_end", blocked_before_count=len(blocked_before_analyzer), blocked_after_count=len(blocked_after_analyzer))
    if wandb_run_started:
        _finish_wandb_run(
            len(blocked_before_analyzer), len(blocked_after_analyzer),
            tasks_published=M, tools_added=len(builder_added), requeued=requeued,
        )

    # --- Summary ---
    print("\n--- Demo summary ---")
    print(f"Roundtable → {M} GTM task(s); orchestrator → steps queue; executor ran cycle 1 + cycle 2 steps.")
    print(f"Failed/blocked tasks BEFORE analyzer: {len(blocked_before_analyzer)} task(s)")
    print(f"Builder added: {builder_added}")
    print(f"Requeued: {requeued} task(s)")
    print(f"Failed/blocked tasks AFTER analyzer: {len(blocked_after_analyzer)} task(s)")
    print("(Step outcomes published to fullsend.worker.results.worked / .failed; analyst report explains before/after.)")


if __name__ == "__main__":
    main()
