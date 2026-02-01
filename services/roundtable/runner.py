"""Roundtable loop: ARTIST, BUSINESS, TECH take turns; same LLM, different prompts."""

import logging
import re

import weave
from langchain_core.messages import HumanMessage, SystemMessage

from .llm import get_llm
from .personas import ROLES, get_persona

logger = logging.getLogger(__name__)

weave.init("viswanathkothe-syracuse-university/weavehacks")


@weave.op
def run_roundtable(
    topic: str,
    max_rounds: int = 2,
    seed_context: str | None = None,
    publish_to: str = "orchestrator",
    builder_context: dict | None = None,
):
    """
    Run the roundtable: each role (ARTIST, BUSINESS, TECH) speaks in turn for max_rounds.
    Same LLM, different system prompt per role. Optional seed_context (e.g. from Redis) prepended once.
    publish_to: "orchestrator" (default), "builder", or "none" — where to publish the summary tasks.
    builder_context: when publish_to=="builder", optional { "blocked_context": list } to enrich builder queue messages.
    """
    llm = get_llm()
    transcript: list[dict[str, str]] = []

    initial = topic.strip()
    if seed_context and seed_context.strip():
        initial = f"Context:\n{seed_context.strip()}\n\nTopic: {topic.strip()}"

    for round_num in range(max_rounds):
        for role in ROLES:
            persona = get_persona(role)
            messages = [
                SystemMessage(content=persona),
                HumanMessage(content=initial),
            ]
            for entry in transcript:
                messages.append(
                    HumanMessage(content=f"[{entry['role'].upper()}] {entry['content']}")
                )
            messages.append(
                HumanMessage(content=f"Your turn as {role.upper()}. Reply in character.")
            )

            response = llm.invoke(messages)
            content = response.content if hasattr(response, "content") else str(response)
            transcript.append({"role": role, "content": content.strip()})

    # Summarizer: GTM tasks (orchestrator) vs builder tasks (analyzer → builder queue)
    if publish_to == "builder":
        summarizer_system = """You are a summarizer for a builder queue consumed by a Claude Code instance. Given the roundtable transcript (about what tools to build so blocked GTM tasks can run), output 3–5 clear builder instructions in a format Claude Code can execute directly: one actionable instruction per line.
Constraints:
- Each line must be one concrete instruction a Claude Code instance can implement (e.g. "Build a HubSpot sync agent that exposes X and Y", "Add a skill that runs Airflow DAGs for scheduling").
- Communicate so a builder agent knows exactly what to build: tool name, capability, and how it unblocks the blocked tasks.
- Output must be at most 10–15 lines total.
No preamble—only this format (builder task format for Claude Code):
Do this first: [one clear builder instruction]
Do this next: [...]
Do this third: [...]
(Do this fourth / Do this fifth only if needed; keep total to 3–5 and 10–15 lines.)"""
        human_content = "Output 3–5 builder tasks (what to build) in the required format so a Claude Code instance can execute each line (max 10–15 lines)."
    else:
        summarizer_system = """You are a summarizer for an AI execution layer. Given the roundtable transcript, output 3–5 actionable GTM tasks that AI agents can carry out autonomously (no human hand-holding).
Constraints:
- Tasks must be executable by AI agents (clear, automatable steps).
- Prefer low-cost, high-return options (avoid expensive or vague tasks).
- Output must be at most 10–15 lines total.
No preamble—only this format:
Do this first: [one concrete, autonomous, cost-conscious task]
Do this next: [...]
Do this third: [...]
(Do this fourth / Do this fifth only if needed; keep total to 3–5 tasks and 10–15 lines.)"""
        human_content = "Output 3–5 actionable tasks in the required format (max 10–15 lines)."

    transcript_text = "\n\n".join(
        f"[{e['role'].upper()}] {e['content']}" for e in transcript
    )
    summary_messages = [
        SystemMessage(content=summarizer_system),
        HumanMessage(content=f"Roundtable transcript:\n\n{transcript_text}\n\n{human_content}"),
    ]
    summary_response = llm.invoke(summary_messages)
    summary = (
        summary_response.content
        if hasattr(summary_response, "content")
        else str(summary_response)
    ).strip()

    # Publish summary tasks to the requested queue (orchestrator, builder, or none)
    blocked_context = (builder_context or {}).get("blocked_context") if builder_context else None
    if publish_to == "orchestrator":
        _publish_tasks_to_orchestrator(summary, topic)
    elif publish_to == "builder":
        _publish_tasks_to_builder(summary, topic, blocked_context=blocked_context)

    return {"transcript": transcript, "summary": summary}


def _parse_summary_into_tasks(summary: str) -> list[str]:
    """Parse 'Do this first: ... Do this next: ...' into list of task strings."""
    pattern = re.compile(
        r"Do this (?:first|next|third|fourth|fifth):\s*(.+?)(?=Do this (?:first|next|third|fourth|fifth):|$)",
        re.DOTALL | re.IGNORECASE,
    )
    tasks = [m.group(1).strip() for m in pattern.finditer(summary) if m.group(1).strip()]
    return tasks


def _publish_tasks_to_orchestrator(summary: str, topic: str) -> None:
    """If RABBITMQ_URL is set, parse summary into tasks and publish each to orchestrator queue."""
    import os
    if not os.getenv("RABBITMQ_URL"):
        logger.info("RABBITMQ_URL not set; skipping publish to orchestrator queue (tasks only printed)")
        return
    try:
        from services.orchestrator_queue import OrchestratorQueue
        queue = OrchestratorQueue()
        queue.connect()
        tasks = _parse_summary_into_tasks(summary)
        for i, task in enumerate(tasks, start=1):
            queue.publish_task({"task": task, "topic": topic}, order=i)
        queue.disconnect()
        logger.info("Published %d tasks to orchestrator queue", len(tasks))
    except Exception as e:
        logger.warning("Orchestrator queue publish failed (roundtable result unchanged): %s", e)


def _publish_tasks_to_builder(summary: str, topic: str, blocked_context: list[dict] | None = None) -> None:
    """If RABBITMQ_URL is set, parse summary into tasks and publish each to builder queue (enriched for Claude Code)."""
    import os
    if not os.getenv("RABBITMQ_URL"):
        logger.info("RABBITMQ_URL not set; skipping publish to builder queue (tasks only printed)")
        return
    try:
        from services.builder_queue import BuilderQueue
        queue = BuilderQueue()
        queue.connect()
        tasks = _parse_summary_into_tasks(summary)
        for i, task in enumerate(tasks, start=1):
            queue.publish_task(
                {"task": task, "topic": topic},
                order=i,
                topic=topic,
                blocked_context=blocked_context,
            )
        queue.disconnect()
        logger.info("Published %d tasks to builder queue", len(tasks))
    except Exception as e:
        logger.warning("Builder queue publish failed (roundtable result unchanged): %s", e)
