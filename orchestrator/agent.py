"""
LangChain agent that uses the orchestrator LLM and Redis via the official
redis-mcp-server (MCP tools). Redis must be running at localhost:6379.

Install: pip install langchain-mcp-adapters redis-mcp-server
Run: python agent.py
"""
from dotenv import load_dotenv
load_dotenv()

import asyncio
import os
import weave
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

# Redis at localhost:6379 — redis-mcp-server is spawned via stdio and exposes MCP tools
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Weave/W&B monitoring (same project as orchestrator.py)
weave.init("viswanathkothe-syracuse-university/weavehacks")


def get_llm():
    """Same LLM config as orchestrator.py (W&B Inference)."""
    return ChatOpenAI(
        base_url=os.getenv("OPENAI_API_BASE", "https://api.inference.wandb.ai/v1"),
        api_key=os.getenv("WANDB_KEY") or os.getenv("OPENAI_API_KEY"),
        model=os.getenv("OPENAI_MODEL", "openai/gpt-oss-120b"),
        temperature=0.7,
    )


async def get_mcp_tools():
    """Load tools from redis-mcp-server (official Redis MCP Server) connected to localhost:6379."""
    # Stdio: spawn redis-mcp-server; it connects to Redis at REDIS_URL.
    # Use "uv run" (from PyPI on the fly) or "redis-mcp-server" if installed via pip.
    use_uv = os.getenv("REDIS_MCP_USE_UV", "1").strip().lower() in ("1", "true", "yes")
    if use_uv:
        client = MultiServerMCPClient({
            "redis": {
                "command": "uv",
                "args": ["run", "redis-mcp-server", "--url", REDIS_URL],
                "transport": "stdio",
            }
        })
    else:
        client = MultiServerMCPClient({
            "redis": {
                "command": "redis-mcp-server",
                "args": ["--url", REDIS_URL],
                "transport": "stdio",
            }
        })
    tools = await client.get_tools(server_name="redis")
    return tools


async def build_agent():
    llm = get_llm()
    tools = await get_mcp_tools()
    return create_react_agent(llm, tools)


AGENT_SYSTEM = """You are the GTM orchestrator agent for Fullsend. You have access to Redis (via MCP tools) at localhost:6379.
Use the Redis tools to store and retrieve data: strings, hashes, lists, sets, streams, JSON, etc.
Use them to save learnings, hypotheses, and context. Be concise and action-oriented."""


@weave.op
async def agent_turn(agent, user_input: str):
    """One agent turn (traced in Weave/W&B)."""
    messages = [SystemMessage(content=AGENT_SYSTEM), HumanMessage(content=user_input)]
    result = await agent.ainvoke({"messages": messages})
    return result


async def main():
    agent = await build_agent()
    print("GTM Orchestrator agent (LangChain + redis-mcp-server → localhost:6379). Type 'quit' to exit.\n")
    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input or user_input.lower() in ("quit", "exit", "q"):
                break
        except EOFError:
            break
        result = await agent_turn(agent, user_input)
        out_msgs = result.get("messages", []) if isinstance(result, dict) else []
        for m in reversed(out_msgs):
            if hasattr(m, "content") and m.content:
                name = getattr(m, "type", "") or getattr(m.__class__, "__name__", "")
                if name in ("ai", "AIMessage"):
                    print("Agent:", m.content)
                    break
        else:
            print("Agent:", result)


if __name__ == "__main__":
    asyncio.run(main())
