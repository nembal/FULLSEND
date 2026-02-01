"""Tests for Redis Agent monitoring functionality.

Implements the PRD test plan:
1. Basic Test - Metrics processing and storage
2. Threshold Test - Success/failure threshold detection
3. Cooldown Test - Alert deduplication

Uses fakeredis for isolated testing without a real Redis server.
"""

import asyncio
import json
import time
from typing import Any, AsyncGenerator

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeredis

from services.redis_agent.alerts import clear_cooldown, recent_alerts, send_alert
from services.redis_agent.monitor import (
    check_experiment_thresholds,
    evaluate_criterion,
    get_current_metrics,
    process_metric,
    update_aggregations,
)


@pytest_asyncio.fixture
async def redis() -> AsyncGenerator[Any, None]:
    """Create a fake Redis instance for testing."""
    fake_redis = fakeredis.FakeRedis()
    yield fake_redis
    await fake_redis.close()


@pytest.fixture(autouse=True)
def clear_alert_cooldowns():
    """Clear alert cooldowns before each test."""
    clear_cooldown()
    yield
    clear_cooldown()


class TestBasicMetrics:
    """PRD Test Plan: Basic Test - Metrics processing and storage."""

    @pytest.mark.asyncio
    async def test_process_metric_stores_raw_metric(self, redis):
        """Verify metrics are stored in metrics:{experiment_id} list."""
        metric = {
            "experiment_id": "exp_test",
            "event": "email_sent",
            "count": 1,
        }

        await process_metric(redis, metric)

        # Check that metric was stored
        stored = await redis.lrange("metrics:exp_test", 0, -1)
        assert len(stored) == 1

        # Verify content
        stored_metric = json.loads(stored[0])
        assert stored_metric["experiment_id"] == "exp_test"
        assert stored_metric["event"] == "email_sent"
        assert stored_metric["count"] == 1
        assert "received_at" in stored_metric

    @pytest.mark.asyncio
    async def test_process_multiple_metrics(self, redis):
        """Verify multiple metrics are appended to list."""
        metrics = [
            {"experiment_id": "exp_test", "event": "email_sent", "count": 1},
            {"experiment_id": "exp_test", "event": "email_opened", "count": 1},
        ]

        for metric in metrics:
            await process_metric(redis, metric)

        stored = await redis.lrange("metrics:exp_test", 0, -1)
        assert len(stored) == 2

    @pytest.mark.asyncio
    async def test_update_aggregations_event_count(self, redis):
        """Verify event counts are aggregated."""
        exp_id = "exp_test"

        # Send multiple events
        await update_aggregations(redis, exp_id, {"event": "email_sent"})
        await update_aggregations(redis, exp_id, {"event": "email_sent"})
        await update_aggregations(redis, exp_id, {"event": "email_opened"})

        # Check aggregations
        sent_count = await redis.hget(f"metrics_aggregated:{exp_id}", "email_sent_count")
        opened_count = await redis.hget(f"metrics_aggregated:{exp_id}", "email_opened_count")

        assert int(sent_count) == 2
        assert int(opened_count) == 1

    @pytest.mark.asyncio
    async def test_update_aggregations_numeric_values(self, redis):
        """Verify numeric values are aggregated with sum/count/latest."""
        exp_id = "exp_test"

        await update_aggregations(redis, exp_id, {"response_rate": 0.10})
        await update_aggregations(redis, exp_id, {"response_rate": 0.15})
        await update_aggregations(redis, exp_id, {"response_rate": 0.20})

        agg_key = f"metrics_aggregated:{exp_id}"
        sum_val = await redis.hget(agg_key, "response_rate_sum")
        count_val = await redis.hget(agg_key, "response_rate_count")
        latest_val = await redis.hget(agg_key, "response_rate_latest")

        assert float(sum_val) == pytest.approx(0.45)
        assert int(count_val) == 3
        assert float(latest_val) == 0.20

    @pytest.mark.asyncio
    async def test_get_current_metrics_computes_averages(self, redis):
        """Verify get_current_metrics computes averages from sum/count."""
        exp_id = "exp_test"

        await update_aggregations(redis, exp_id, {"response_rate": 0.10})
        await update_aggregations(redis, exp_id, {"response_rate": 0.20})

        metrics = await get_current_metrics(redis, exp_id)

        # Should have average computed
        assert "response_rate_avg" in metrics
        assert metrics["response_rate_avg"] == pytest.approx(0.15)
        assert metrics["response_rate_latest"] == 0.20

    @pytest.mark.asyncio
    async def test_metric_without_experiment_id_skipped(self, redis):
        """Verify metrics without experiment_id are gracefully skipped."""
        metric = {"event": "email_sent", "count": 1}  # Missing experiment_id

        await process_metric(redis, metric)

        # Should not create any keys
        keys = await redis.keys("metrics:*")
        assert len(keys) == 0


class TestThresholdDetection:
    """PRD Test Plan: Threshold Test - Success/failure threshold detection."""

    @pytest.mark.asyncio
    async def test_evaluate_criterion_greater_than(self, redis):
        """Test criterion evaluation: > operator."""
        metrics = {"response_rate": 0.15}

        assert evaluate_criterion("response_rate > 0.10", metrics) is True
        assert evaluate_criterion("response_rate > 0.20", metrics) is False

    @pytest.mark.asyncio
    async def test_evaluate_criterion_less_than(self, redis):
        """Test criterion evaluation: < operator."""
        metrics = {"response_rate": 0.05}

        assert evaluate_criterion("response_rate < 0.10", metrics) is True
        assert evaluate_criterion("response_rate < 0.02", metrics) is False

    @pytest.mark.asyncio
    async def test_evaluate_criterion_with_latest_suffix(self, redis):
        """Test criterion lookup with _latest suffix fallback."""
        metrics = {"response_rate_latest": 0.15}

        # Should find response_rate via _latest suffix
        assert evaluate_criterion("response_rate > 0.10", metrics) is True

    @pytest.mark.asyncio
    async def test_evaluate_criterion_with_avg_suffix(self, redis):
        """Test criterion lookup with _avg suffix fallback."""
        metrics = {"response_rate_avg": 0.15}

        # Should find response_rate via _avg suffix
        assert evaluate_criterion("response_rate > 0.10", metrics) is True

    @pytest.mark.asyncio
    async def test_evaluate_criterion_missing_metric(self, redis):
        """Test criterion with missing metric returns False."""
        metrics = {"other_metric": 0.15}

        assert evaluate_criterion("response_rate > 0.10", metrics) is False

    @pytest.mark.asyncio
    async def test_evaluate_criterion_all_operators(self, redis):
        """Test all supported operators."""
        metrics = {"value": 10.0}

        assert evaluate_criterion("value > 5", metrics) is True
        assert evaluate_criterion("value < 15", metrics) is True
        assert evaluate_criterion("value >= 10", metrics) is True
        assert evaluate_criterion("value <= 10", metrics) is True
        assert evaluate_criterion("value == 10", metrics) is True
        assert evaluate_criterion("value != 5", metrics) is True

    @pytest.mark.asyncio
    async def test_check_experiment_thresholds_success(self, redis):
        """PRD Test: Create experiment with thresholds, verify success alert."""
        exp_id = "exp_test"

        # Set up experiment with success criteria
        await redis.hset(
            f"experiments:{exp_id}",
            mapping={
                "hypothesis": "Test experiment",
                "success_criteria": json.dumps(["response_rate > 0.10"]),
                "failure_criteria": json.dumps(["response_rate < 0.02"]),
                "status": "active",
            },
        )

        # Add metrics that cross success threshold
        await update_aggregations(redis, exp_id, {"response_rate": 0.15})

        # Track published messages
        published = []
        original_publish = redis.publish

        async def mock_publish(channel, message):
            published.append({"channel": channel, "message": json.loads(message)})
            return await original_publish(channel, message)

        redis.publish = mock_publish

        # Check thresholds
        exp = {
            "id": exp_id,
            "success_criteria": ["response_rate > 0.10"],
            "failure_criteria": ["response_rate < 0.02"],
        }
        await check_experiment_thresholds(redis, exp)

        # Should see success_threshold alert
        assert len(published) == 1
        assert published[0]["message"]["type"] == "success_threshold"
        assert published[0]["message"]["experiment_id"] == exp_id
        assert "response_rate > 0.10" in published[0]["message"]["criterion"]

    @pytest.mark.asyncio
    async def test_check_experiment_thresholds_failure(self, redis):
        """PRD Test: Verify failure threshold detection."""
        exp_id = "exp_test"

        # Add metrics that cross failure threshold
        await update_aggregations(redis, exp_id, {"response_rate": 0.01})

        published = []
        original_publish = redis.publish

        async def mock_publish(channel, message):
            published.append({"channel": channel, "message": json.loads(message)})
            return await original_publish(channel, message)

        redis.publish = mock_publish

        exp = {
            "id": exp_id,
            "success_criteria": ["response_rate > 0.10"],
            "failure_criteria": ["response_rate < 0.02"],
        }
        await check_experiment_thresholds(redis, exp)

        # Should see failure_threshold alert
        assert len(published) == 1
        assert published[0]["message"]["type"] == "failure_threshold"
        assert published[0]["message"]["severity"] == "high"


class TestAlertCooldown:
    """PRD Test Plan: Cooldown Test - Alert deduplication."""

    @pytest.mark.asyncio
    async def test_alert_cooldown_blocks_duplicate(self, redis):
        """PRD Test: Send same alert twice quickly, second should be blocked."""
        alert = {
            "type": "error",
            "experiment_id": "exp_test",
            "message": "Test error",
        }

        # First alert should succeed
        result1 = await send_alert(redis, alert.copy())
        assert result1 is True

        # Second alert immediately after should be blocked
        result2 = await send_alert(redis, alert.copy())
        assert result2 is False

    @pytest.mark.asyncio
    async def test_alert_cooldown_different_experiments(self, redis):
        """Different experiments should not share cooldown."""
        alert1 = {
            "type": "error",
            "experiment_id": "exp_1",
            "message": "Test error",
        }
        alert2 = {
            "type": "error",
            "experiment_id": "exp_2",
            "message": "Test error",
        }

        result1 = await send_alert(redis, alert1)
        result2 = await send_alert(redis, alert2)

        # Both should succeed - different experiments
        assert result1 is True
        assert result2 is True

    @pytest.mark.asyncio
    async def test_alert_cooldown_different_types(self, redis):
        """Different alert types should not share cooldown."""
        alert1 = {
            "type": "error",
            "experiment_id": "exp_test",
            "message": "Error",
        }
        alert2 = {
            "type": "success_threshold",
            "experiment_id": "exp_test",
            "message": "Success",
        }

        result1 = await send_alert(redis, alert1)
        result2 = await send_alert(redis, alert2)

        # Both should succeed - different types
        assert result1 is True
        assert result2 is True

    @pytest.mark.asyncio
    async def test_alert_adds_metadata(self, redis):
        """Verify alerts get timestamp and source metadata."""
        published = []
        original_publish = redis.publish

        async def mock_publish(channel, message):
            published.append({"channel": channel, "message": json.loads(message)})
            return await original_publish(channel, message)

        redis.publish = mock_publish

        alert = {
            "type": "error",
            "experiment_id": "exp_test",
            "message": "Test error",
        }
        await send_alert(redis, alert)

        assert len(published) == 1
        msg = published[0]["message"]
        assert msg["source"] == "redis_agent"
        assert "timestamp" in msg
        assert published[0]["channel"] == "fullsend:to_orchestrator"

    @pytest.mark.asyncio
    async def test_error_event_triggers_alert(self, redis):
        """Verify error events in metrics stream trigger immediate alerts."""
        published = []
        original_publish = redis.publish

        async def mock_publish(channel, message):
            published.append({"channel": channel, "message": json.loads(message)})
            return await original_publish(channel, message)

        redis.publish = mock_publish

        metric = {
            "experiment_id": "exp_test",
            "event": "error",
            "message": "Connection failed",
        }

        await process_metric(redis, metric)

        # Should see error alert
        assert len(published) == 1
        assert published[0]["message"]["type"] == "error"
        assert published[0]["message"]["severity"] == "high"
        assert "Connection failed" in published[0]["message"]["message"]
