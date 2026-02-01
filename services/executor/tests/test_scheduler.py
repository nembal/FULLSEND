"""Unit tests for the scheduler module.

Tests cron parsing with:
- Basic cron expression matching
- Various cron patterns (every minute, hourly, daily, weekly)
- Edge cases at minute boundaries
"""

from datetime import datetime, timedelta

import pytest

from services.executor.scheduler import should_run_now


class TestShouldRunNow:
    """Tests for should_run_now function."""

    def test_every_minute_matches(self):
        """Test '* * * * *' matches any current time."""
        now = datetime(2026, 2, 1, 12, 30, 0)
        cron_expr = "* * * * *"

        result = should_run_now(cron_expr, now)

        assert result is True

    def test_exact_minute_match(self):
        """Test specific minute matches correctly."""
        # Cron: at minute 30 of every hour
        cron_expr = "30 * * * *"

        # Test at exactly 12:30 - should match
        now = datetime(2026, 2, 1, 12, 30, 0)
        assert should_run_now(cron_expr, now) is True

        # Test at 12:31 - should NOT match (outside 1 minute window)
        now = datetime(2026, 2, 1, 12, 31, 30)
        assert should_run_now(cron_expr, now) is False

    def test_hourly_at_9am(self):
        """Test '0 9 * * *' runs at 9:00 AM."""
        cron_expr = "0 9 * * *"

        # At 9:00 - should match
        now = datetime(2026, 2, 1, 9, 0, 0)
        assert should_run_now(cron_expr, now) is True

        # At 9:00:30 - still within window
        now = datetime(2026, 2, 1, 9, 0, 30)
        assert should_run_now(cron_expr, now) is True

        # At 8:59 - too early
        now = datetime(2026, 2, 1, 8, 59, 0)
        assert should_run_now(cron_expr, now) is False

        # At 9:01 - too late
        now = datetime(2026, 2, 1, 9, 1, 30)
        assert should_run_now(cron_expr, now) is False

    def test_weekly_monday_9am(self):
        """Test '0 9 * * MON' runs on Mondays at 9:00 AM."""
        cron_expr = "0 9 * * MON"

        # Monday 2026-02-02 at 9:00 AM - should match
        monday = datetime(2026, 2, 2, 9, 0, 0)
        assert should_run_now(cron_expr, monday) is True

        # Tuesday 2026-02-03 at 9:00 AM - wrong day
        tuesday = datetime(2026, 2, 3, 9, 0, 0)
        assert should_run_now(cron_expr, tuesday) is False

    def test_daily_at_midnight(self):
        """Test '0 0 * * *' runs at midnight."""
        cron_expr = "0 0 * * *"

        now = datetime(2026, 2, 1, 0, 0, 30)
        assert should_run_now(cron_expr, now) is True

        now = datetime(2026, 2, 1, 0, 1, 30)
        assert should_run_now(cron_expr, now) is False

    def test_every_5_minutes(self):
        """Test '*/5 * * * *' runs every 5 minutes."""
        cron_expr = "*/5 * * * *"

        # At minute 0 - matches
        now = datetime(2026, 2, 1, 12, 0, 0)
        assert should_run_now(cron_expr, now) is True

        # At minute 5 - matches
        now = datetime(2026, 2, 1, 12, 5, 0)
        assert should_run_now(cron_expr, now) is True

        # At minute 10 - matches
        now = datetime(2026, 2, 1, 12, 10, 0)
        assert should_run_now(cron_expr, now) is True

        # At minute 3 - does not match
        now = datetime(2026, 2, 1, 12, 3, 0)
        assert should_run_now(cron_expr, now) is False

    def test_specific_days_of_month(self):
        """Test '0 9 1,15 * *' runs on 1st and 15th at 9 AM."""
        cron_expr = "0 9 1,15 * *"

        # February 1st at 9 AM - matches
        now = datetime(2026, 2, 1, 9, 0, 0)
        assert should_run_now(cron_expr, now) is True

        # February 15th at 9 AM - matches
        now = datetime(2026, 2, 15, 9, 0, 0)
        assert should_run_now(cron_expr, now) is True

        # February 2nd at 9 AM - wrong day of month
        now = datetime(2026, 2, 2, 9, 0, 0)
        assert should_run_now(cron_expr, now) is False

    def test_window_boundary_just_before(self):
        """Test that we're within the 60-second window."""
        cron_expr = "30 12 * * *"

        # At 12:29:01 - next run is 12:30:00, 59 seconds away - should match
        now = datetime(2026, 2, 1, 12, 29, 1)
        assert should_run_now(cron_expr, now) is True

        # At 12:30:59 - we are at 12:30, still within window
        now = datetime(2026, 2, 1, 12, 30, 59)
        assert should_run_now(cron_expr, now) is True

    def test_invalid_cron_expression(self):
        """Test that invalid cron expressions raise an error."""
        with pytest.raises(Exception):
            should_run_now("invalid cron", datetime.now())

    def test_complex_expression(self):
        """Test complex cron expression with ranges."""
        # Every weekday at 9:30 AM
        cron_expr = "30 9 * * 1-5"

        # Monday at 9:30 - matches
        monday = datetime(2026, 2, 2, 9, 30, 0)  # Feb 2, 2026 is Monday
        assert should_run_now(cron_expr, monday) is True

        # Saturday at 9:30 - does not match (weekends excluded)
        saturday = datetime(2026, 2, 7, 9, 30, 0)  # Feb 7, 2026 is Saturday
        assert should_run_now(cron_expr, saturday) is False
