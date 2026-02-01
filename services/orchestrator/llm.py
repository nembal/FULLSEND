"""
Orchestrator LLM (different from roundtable). Uses OpenAI-compatible API.
Configure via OPENAI_API_KEY or ORCHESTRATOR_LLM_API_KEY, ORCHESTRATOR_LLM_MODEL, optional ORCHESTRATOR_LLM_BASE_URL.
"""

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()


def get_orchestrator_llm():
    """Return ChatOpenAI for orchestrator (steps). Prefer OPENAI_API_KEY or ORCHESTRATOR_LLM_API_KEY; if unset, fall back to W&B (WANDB_KEY) for testing."""
    api_key = os.getenv("ORCHESTRATOR_LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if api_key:
        model = os.getenv("ORCHESTRATOR_LLM_MODEL", "gpt-4o-mini")
        base_url = os.getenv("ORCHESTRATOR_LLM_BASE_URL")
        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url if base_url else None,
            temperature=0.2,
        )
    # Fallback: W&B (same as roundtable) so orchestrator runs with only WANDB_KEY
    wandb_key = os.getenv("WANDB_KEY")
    if not wandb_key:
        raise ValueError(
            "Set ORCHESTRATOR_LLM_API_KEY or OPENAI_API_KEY for orchestrator LLM, or WANDB_KEY to use W&B."
        )
    return ChatOpenAI(
        base_url=os.getenv("OPENAI_API_BASE", "https://api.inference.wandb.ai/v1"),
        api_key=wandb_key,
        model=os.getenv("ORCHESTRATOR_LLM_MODEL") or os.getenv("OPENAI_MODEL", "openai/gpt-oss-120b"),
        temperature=0.2,
    )
