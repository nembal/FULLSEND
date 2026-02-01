"""Roundtable loop: ARTIST, BUSINESS, TECH take turns; same LLM, different prompts."""

import os

import weave
from langchain_core.messages import HumanMessage, SystemMessage

from .llm import get_llm
from .personas import ROLES, get_persona, get_summarizer_prompt

weave.init(os.getenv("WEAVE_PROJECT", "fullsend/roundtable"))


@weave.op
def run_roundtable(
    prompt: str,
    context: str = "",
    learnings: list[str] | None = None,
    max_rounds: int = 3,
):
    """
    Run the roundtable: each role (ARTIST, BUSINESS, TECH) speaks in turn for max_rounds.
    Same LLM, different system prompt per role.

    Args:
        prompt: The topic or question to debate
        context: Optional context string (e.g. background info)
        learnings: Optional list of learnings from past experiments
        max_rounds: Number of debate rounds (default: 3)

    Returns:
        dict with:
            - transcript: Formatted string with round headers
            - summary: List of actionable tasks with owners
    """
    llm = get_llm()
    learnings = learnings or []

    # Build initial context block (PRD format)
    debate_context = f"""## Topic
{prompt}
"""
    if context:
        debate_context += f"""
## Context
{context}
"""
    if learnings:
        debate_context += f"""
## Learnings from Past Experiments
{chr(10).join(f"- {l}" for l in learnings)}
"""

    transcript_parts: list[str] = []

    for round_num in range(max_rounds):
        # Add round header (PRD format)
        transcript_parts.append(f"\n--- Round {round_num + 1} ---\n")

        for role in ROLES:
            persona = get_persona(role)

            # Build conversation so far
            history = "".join(transcript_parts)

            # Build agent prompt
            agent_prompt = f"""{debate_context}

## Debate So Far
{history}

## Your Turn
Respond to the topic. Build on or challenge previous points.
Keep it concise (2-3 sentences). Be distinctive to your persona."""

            messages = [
                SystemMessage(content=persona),
                HumanMessage(content=agent_prompt),
            ]

            response = llm.invoke(messages)
            content = response.content if hasattr(response, "content") else str(response)
            transcript_parts.append(f"{role.upper()}: {content.strip()}\n")

    # Format transcript as string (PRD format)
    transcript = "".join(transcript_parts)

    # Summarizer agent: use prompt from file (includes owner assignment rules)
    summarizer_prompt = get_summarizer_prompt()

    summary_messages = [
        SystemMessage(content=summarizer_prompt),
        HumanMessage(content=f"""## Debate Transcript
{transcript}

## Output
List 3-5 actionable tasks. Each should be specific and executable.
Format as a simple list:
- Task description (Owner: who)"""),
    ]

    summary_response = llm.invoke(summary_messages)
    summary_text = (
        summary_response.content
        if hasattr(summary_response, "content")
        else str(summary_response)
    ).strip()

    # Parse summary into list (PRD format)
    lines = summary_text.split("\n")
    tasks = [
        line.lstrip("- ").strip()
        for line in lines
        if line.strip().startswith("-")
    ]
    # Ensure max 5 tasks
    summary = tasks[:5] if tasks else [summary_text]

    return {"transcript": transcript, "summary": summary}
