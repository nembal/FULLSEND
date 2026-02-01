"""Alert generation and sending for Redis Agent.

Handles:
- Alert deduplication with cooldown
- Publishing alerts to Orchestrator
"""

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis

from .config import get_settings

logger = logging.getLogger(__name__)

# Lazy settings getter
_settings = None

def _get_settings():
    global _settings
    if _settings is None:
        _settings = get_settings()
    return _settings

# Track recent alerts to avoid spam
# Key: "{experiment_id}:{alert_type}" -> Value: timestamp of last send
recent_alerts: dict[str, float] = {}


async def send_alert(redis: Redis, alert: dict[str, Any]) -> bool:
    """Send alert to Orchestrator with cooldown.

    Returns True if alert was sent, False if skipped due to cooldown.
    """
    # Create alert key for deduplication
    exp_id = alert.get("experiment_id", "unknown")
    alert_type = alert.get("type", "unknown")
    alert_key = f"{exp_id}:{alert_type}"

    # Check cooldown
    last_sent = recent_alerts.get(alert_key, 0)
    elapsed = time.time() - last_sent

    if elapsed < _get_settings().alert_cooldown_seconds:
        logger.debug(
            f"Alert skipped (cooldown): {alert_key}, "
            f"{_get_settings().alert_cooldown_seconds - elapsed:.0f}s remaining"
        )
        return False

    # Update cooldown tracker
    recent_alerts[alert_key] = time.time()

    # Add metadata
    alert["timestamp"] = datetime.now(UTC).isoformat()
    alert["source"] = "redis_agent"

    # Publish to Orchestrator
    message = json.dumps(alert)
    await redis.publish(_get_settings().orchestrator_channel, message)

    logger.info(f"Alert sent: {alert_type} for {exp_id}")
    logger.debug(f"Alert payload: {message}")

    return True


def clear_cooldown(exp_id: str | None = None, alert_type: str | None = None) -> None:
    """Clear cooldown for specific alerts (useful for testing).

    Args:
        exp_id: Clear cooldowns for this experiment (None = all)
        alert_type: Clear cooldowns for this type (None = all types)
    """
    global recent_alerts

    if exp_id is None and alert_type is None:
        recent_alerts.clear()
        return

    keys_to_remove = []
    for key in recent_alerts:
        key_exp, key_type = key.rsplit(":", 1)
        if exp_id and key_exp != exp_id:
            continue
        if alert_type and key_type != alert_type:
            continue
        keys_to_remove.append(key)

    for key in keys_to_remove:
        del recent_alerts[key]
