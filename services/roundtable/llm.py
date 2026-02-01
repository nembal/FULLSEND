"""Single LLM for roundtable (W&B Inference only). Same config as redis agent."""

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()


def get_llm():
    """W&B Inference LLM (openai/gpt-oss-120b). Same for all three personas."""
    api_key = os.getenv("WANDB_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("Missing API key: set WANDB_KEY or OPENAI_API_KEY environment variable")
    return ChatOpenAI(
        base_url=os.getenv("OPENAI_API_BASE", "https://api.inference.wandb.ai/v1"),
        api_key=api_key,
        model=os.getenv("OPENAI_MODEL", "openai/gpt-oss-120b"),
        temperature=0.7,
    )
