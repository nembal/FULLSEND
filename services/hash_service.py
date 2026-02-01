"""
Generate random hashes/UUIDs for orchestrator task IDs.
Used by the orchestrator agent to assign a unique ID to each consumed task.
"""

import secrets
import uuid


def generate_task_id() -> str:
    """Return a random hex string suitable as a unique task/run ID (UUID-like)."""
    return uuid.uuid4().hex


def generate_task_id_hash() -> str:
    """Return a 32-char hex hash (alternative to UUID hex)."""
    return secrets.token_hex(16)
