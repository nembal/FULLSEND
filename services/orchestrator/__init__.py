"""Orchestrator service - strategic manager for the Fullsend GTM system.

Maintains context, prioritizes work, dispatches tasks to FULLSEND and Builder.
"""

__all__ = [
    "main",
    "OrchestratorAgent",
    "Context",
    "load_context",
    "load_context_safe",
    "Dispatcher",
    "Decision",
    "execute_decision",
    "ThinkingTimeoutError",
    "Settings",
]
