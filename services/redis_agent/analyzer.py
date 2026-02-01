"""LLM-powered analysis for Redis Agent using Gemini 2.0 Flash.

Handles:
- Periodic summaries of all active experiments
- Individual experiment analysis
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from redis.asyncio import Redis

from .config import get_settings
from .monitor import get_active_experiments, get_current_metrics

logger = logging.getLogger(__name__)

# Lazy settings getter
_settings = None

def _get_settings():
    global _settings
    if _settings is None:
        _settings = get_settings()
    return _settings

# Load prompts from files
_prompts_dir = Path(__file__).parent / "prompts"


def _load_prompt(name: str) -> str:
    """Load a prompt template from the prompts directory."""
    path = _prompts_dir / f"{name}.txt"
    if path.exists():
        return path.read_text()
    return ""


_summarize_prompt = _load_prompt("summarize")


def _format_metrics_brief(metrics: dict[str, Any]) -> str:
    """Format metrics in a brief format for summaries."""
    if not metrics:
        return "no metrics yet"

    parts = []
    for key, value in metrics.items():
        if key in ("last_updated",):
            continue
        if isinstance(value, float):
            parts.append(f"{key}={value:.3f}")
        else:
            parts.append(f"{key}={value}")

    return ", ".join(parts[:5]) if parts else "no metrics yet"


async def generate_summary(redis: Redis, experiments: list[dict[str, Any]]) -> str:
    """Generate LLM summary of all active experiments.

    Uses Gemini 2.0 Flash for cheap, fast analysis.
    """
    # Build experiment summaries
    summaries = []
    for exp in experiments:
        exp_id = exp.get("id", "unknown")
        metrics = await get_current_metrics(redis, exp_id)
        summaries.append(f"- {exp_id}: {_format_metrics_brief(metrics)}")

    prompt = f"""{_summarize_prompt}

## Active Experiments
{chr(10).join(summaries)}

Focus on: wins, concerns, and recommendations."""

    # Check if Gemini API is configured
    if not _get_settings().google_api_key:
        logger.warning("GOOGLE_API_KEY not set, using mock summary")
        return f"Summary of {len(experiments)} experiments (Gemini not configured)"

    try:
        import google.generativeai as genai

        genai.configure(api_key=_get_settings().google_api_key)
        model = genai.GenerativeModel(_get_settings().redis_agent_model)

        # Run in thread to avoid blocking
        response = await asyncio.to_thread(
            model.generate_content,
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.2,
                max_output_tokens=200,
            ),
        )

        return response.text

    except ImportError:
        logger.error("google-generativeai package not installed")
        return f"Summary of {len(experiments)} experiments (missing google-generativeai)"
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return f"Summary of {len(experiments)} experiments (API error: {e})"


async def run_periodic_summaries(redis: Redis) -> None:
    """Generate periodic summaries of all experiments.

    Runs on SUMMARY_INTERVAL_SECONDS interval (default: 1 hour).
    Publishes summary to fullsend:to_orchestrator channel.
    """
    logger.info(
        f"Starting periodic summaries (interval: {_get_settings().summary_interval_seconds}s)"
    )

    while True:
        # Sleep first (summaries at interval, not immediately)
        await asyncio.sleep(_get_settings().summary_interval_seconds)

        try:
            experiments = await get_active_experiments(redis)

            if not experiments:
                logger.debug("No active experiments, skipping summary")
                continue

            logger.info(f"Generating summary for {len(experiments)} experiments")
            summary = await generate_summary(redis, experiments)

            # Publish to orchestrator
            message = json.dumps(
                {
                    "type": "periodic_summary",
                    "source": "redis_agent",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "summary": summary,
                    "experiment_count": len(experiments),
                }
            )

            await redis.publish(_get_settings().orchestrator_channel, message)
            logger.info(f"Published periodic summary: {summary[:100]}...")

        except Exception as e:
            logger.error(f"Error generating periodic summary: {e}")


async def analyze_experiment_metrics(redis: Redis, exp_id: str) -> str:
    """Use LLM to analyze experiment metrics and generate insights.

    This is for on-demand analysis of a specific experiment.
    """
    from .monitor import get_metrics_spec

    # Load analyze prompt
    analyze_prompt = _load_prompt("analyze")

    # Get experiment data
    exp_key = f"experiments:{exp_id}"
    exp_data = await redis.hgetall(exp_key)

    if not exp_data:
        return f"Experiment {exp_id} not found"

    # Decode experiment data
    exp = {}
    for k, v in exp_data.items():
        if isinstance(k, bytes):
            k = k.decode("utf-8")
        if isinstance(v, bytes):
            v = v.decode("utf-8")
        try:
            exp[k] = json.loads(v)
        except json.JSONDecodeError:
            exp[k] = v

    metrics = await get_current_metrics(redis, exp_id)
    metrics_spec = await get_metrics_spec(redis, exp_id)

    # Format success/failure criteria
    def format_list(items: list | str) -> str:
        if isinstance(items, str):
            return f"- {items}"
        return "\n".join(f"- {item}" for item in items) if items else "- None defined"

    def format_metrics(m: dict) -> str:
        if not m:
            return "No metrics collected yet"
        return "\n".join(f"- {k}: {v}" for k, v in m.items())

    prompt = f"""{analyze_prompt}

## Experiment
ID: {exp_id}
Hypothesis: {exp.get('hypothesis', 'Unknown')}
Target: {exp.get('target', {}).get('description', 'Unknown') if isinstance(exp.get('target'), dict) else exp.get('target', 'Unknown')}

## Success Criteria
{format_list(exp.get('success_criteria', []))}

## Failure Criteria
{format_list(exp.get('failure_criteria', []))}

## Current Metrics
{format_metrics(metrics)}

## Task
1. Are we trending toward success or failure?
2. Any anomalies or patterns?
3. Recommendations (if any)?

Be concise. Facts only. No fluff."""

    # Check if Gemini API is configured
    if not _get_settings().google_api_key:
        logger.warning("GOOGLE_API_KEY not set, using mock analysis")
        return f"Analysis of {exp_id} (Gemini not configured)"

    try:
        import google.generativeai as genai

        genai.configure(api_key=_get_settings().google_api_key)
        model = genai.GenerativeModel(_get_settings().redis_agent_model)

        response = await asyncio.to_thread(
            model.generate_content,
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.2,
                max_output_tokens=500,
            ),
        )

        return response.text

    except ImportError:
        logger.error("google-generativeai package not installed")
        return f"Analysis of {exp_id} (missing google-generativeai)"
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return f"Analysis of {exp_id} (API error: {e})"
