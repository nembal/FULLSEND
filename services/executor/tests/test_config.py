"""Unit tests for the config module."""

import os

import pytest
from pydantic import ValidationError

from services.executor.config import Settings, get_settings


class TestSettings:
    """Tests for Settings class."""

    def test_default_values(self, monkeypatch):
        """Test Settings has sensible defaults."""
        # Clear any env vars that might affect settings
        for key in ["REDIS_URL", "SCHEDULE_MODE", "SPEEDRUN_INTERVAL"]:
            monkeypatch.delenv(key, raising=False)

        settings = Settings()

        assert settings.redis_url == "redis://localhost:6379"
        assert settings.schedule_mode == "trigger"
        assert settings.speedrun_interval == 5
        assert settings.speedrun_max_per_cycle == 3
        assert settings.cron_check_interval == 60
        assert settings.tool_execution_timeout == 300
        assert settings.retry_max_attempts == 3
        assert settings.retry_backoff_min == 1.0
        assert settings.retry_backoff_max == 30.0

    def test_schedule_mode_trigger(self, monkeypatch):
        """Test trigger schedule mode configuration."""
        monkeypatch.setenv("SCHEDULE_MODE", "trigger")
        settings = Settings()
        assert settings.schedule_mode == "trigger"

    def test_schedule_mode_cron(self, monkeypatch):
        """Test cron schedule mode configuration."""
        monkeypatch.setenv("SCHEDULE_MODE", "cron")
        settings = Settings()
        assert settings.schedule_mode == "cron"

    def test_schedule_mode_speedrun(self, monkeypatch):
        """Test speedrun schedule mode configuration."""
        monkeypatch.setenv("SCHEDULE_MODE", "speedrun")
        settings = Settings()
        assert settings.schedule_mode == "speedrun"

    def test_invalid_schedule_mode_raises_error(self, monkeypatch):
        """Test that invalid schedule mode raises ValidationError."""
        monkeypatch.setenv("SCHEDULE_MODE", "invalid_mode")
        with pytest.raises(ValidationError):
            Settings()

    def test_speedrun_interval_bounds(self, monkeypatch):
        """Test speedrun_interval respects bounds."""
        # Valid value
        monkeypatch.setenv("SPEEDRUN_INTERVAL", "10")
        settings = Settings()
        assert settings.speedrun_interval == 10

        # Below minimum should fail
        monkeypatch.setenv("SPEEDRUN_INTERVAL", "0")
        with pytest.raises(ValidationError):
            Settings()

        # Above maximum should fail
        monkeypatch.setenv("SPEEDRUN_INTERVAL", "9999")
        with pytest.raises(ValidationError):
            Settings()

    def test_cron_check_interval_bounds(self, monkeypatch):
        """Test cron_check_interval respects bounds."""
        # Valid value
        monkeypatch.setenv("CRON_CHECK_INTERVAL", "120")
        settings = Settings()
        assert settings.cron_check_interval == 120

        # Below minimum (10) should fail
        monkeypatch.setenv("CRON_CHECK_INTERVAL", "5")
        with pytest.raises(ValidationError):
            Settings()

    def test_tool_execution_timeout_bounds(self, monkeypatch):
        """Test tool_execution_timeout respects bounds."""
        # Valid value
        monkeypatch.setenv("TOOL_EXECUTION_TIMEOUT", "600")
        settings = Settings()
        assert settings.tool_execution_timeout == 600

        # Below minimum should fail
        monkeypatch.setenv("TOOL_EXECUTION_TIMEOUT", "0")
        with pytest.raises(ValidationError):
            Settings()

    def test_retry_max_attempts_bounds(self, monkeypatch):
        """Test retry_max_attempts respects bounds."""
        # Valid value
        monkeypatch.setenv("RETRY_MAX_ATTEMPTS", "5")
        settings = Settings()
        assert settings.retry_max_attempts == 5

        # Below minimum should fail
        monkeypatch.setenv("RETRY_MAX_ATTEMPTS", "0")
        with pytest.raises(ValidationError):
            Settings()

        # Above maximum should fail
        monkeypatch.setenv("RETRY_MAX_ATTEMPTS", "20")
        with pytest.raises(ValidationError):
            Settings()

    def test_backoff_max_must_exceed_backoff_min(self, monkeypatch):
        """Test retry_backoff_max must be >= retry_backoff_min."""
        monkeypatch.setenv("RETRY_BACKOFF_MIN", "10.0")
        monkeypatch.setenv("RETRY_BACKOFF_MAX", "5.0")
        with pytest.raises(ValidationError):
            Settings()

    def test_redis_url_from_env(self, monkeypatch):
        """Test REDIS_URL can be set from environment."""
        monkeypatch.setenv("REDIS_URL", "redis://custom:6380")
        settings = Settings()
        assert settings.redis_url == "redis://custom:6380"

    def test_channel_defaults(self, monkeypatch):
        """Test Redis channel defaults."""
        settings = Settings()
        assert settings.channel_schedules == "fullsend:schedules"
        assert settings.channel_execute_now == "fullsend:execute_now"
        assert settings.channel_metrics == "fullsend:metrics"
        assert settings.channel_experiment_results == "fullsend:experiment_results"


class TestGetModeDescription:
    """Tests for get_mode_description method."""

    def test_trigger_mode_description(self, monkeypatch):
        """Test description for trigger mode."""
        monkeypatch.setenv("SCHEDULE_MODE", "trigger")
        settings = Settings()
        desc = settings.get_mode_description()

        assert "Trigger mode" in desc
        assert "fullsend:execute_now" in desc

    def test_cron_mode_description(self, monkeypatch):
        """Test description for cron mode."""
        monkeypatch.setenv("SCHEDULE_MODE", "cron")
        monkeypatch.setenv("CRON_CHECK_INTERVAL", "120")
        settings = Settings()
        desc = settings.get_mode_description()

        assert "Cron mode" in desc
        assert "120s" in desc

    def test_speedrun_mode_description(self, monkeypatch):
        """Test description for speedrun mode."""
        monkeypatch.setenv("SCHEDULE_MODE", "speedrun")
        monkeypatch.setenv("SPEEDRUN_INTERVAL", "10")
        monkeypatch.setenv("SPEEDRUN_MAX_PER_CYCLE", "5")
        settings = Settings()
        desc = settings.get_mode_description()

        assert "Speedrun mode" in desc
        assert "10s" in desc
        assert "5" in desc


class TestGetSettings:
    """Tests for get_settings factory function."""

    def test_get_settings_returns_settings_instance(self, monkeypatch):
        """Test get_settings returns a Settings instance."""
        # Clear env vars for predictable behavior
        for key in ["SCHEDULE_MODE"]:
            monkeypatch.delenv(key, raising=False)

        settings = get_settings()
        assert isinstance(settings, Settings)
