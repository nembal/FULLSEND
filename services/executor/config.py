"""Configuration module for Executor service using Pydantic Settings.

Schedule Modes:
---------------
1. TRIGGER (default): Wait for explicit execution requests via Redis channel.
   - Listens on `fullsend:execute_now` for execution triggers
   - Also listens on `fullsend:schedules` for schedule updates
   - Best for: Production with external orchestration

2. CRON: Respect cron schedules defined in `schedules:{experiment_id}` Redis keys.
   - Checks schedules every `cron_check_interval` seconds (default: 60)
   - Runs experiments whose cron expression matches current time
   - Best for: Production with time-based scheduling

3. SPEEDRUN: Run experiments continuously for demos/testing.
   - Runs every `speedrun_interval` seconds (default: 5)
   - Runs at most `speedrun_max_per_cycle` experiments per cycle (default: 3)
   - Best for: Demos, development, testing

Environment Variables:
----------------------
SCHEDULE_MODE=trigger        # trigger | cron | speedrun
SPEEDRUN_INTERVAL=5          # seconds between runs in speedrun mode
SPEEDRUN_MAX_PER_CYCLE=3     # max experiments per speedrun cycle
CRON_CHECK_INTERVAL=60       # seconds between schedule checks in cron mode
TOOL_EXECUTION_TIMEOUT=300   # timeout in seconds for tool execution
REDIS_URL=redis://localhost:6379
TOOLS_PATH=/app/tools
"""

from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Get the repo root (two levels up from this file)
REPO_ROOT = Path(__file__).parent.parent.parent
ENV_FILE = REPO_ROOT / ".env"


class ScheduleMode(str, Enum):
    """Execution schedule modes.

    TRIGGER: Wait for explicit execution requests via Redis pub/sub.
    CRON: Respect cron schedules stored in Redis.
    SPEEDRUN: Run experiments continuously (for demos/testing).
    """

    TRIGGER = "trigger"
    CRON = "cron"
    SPEEDRUN = "speedrun"


class Settings(BaseSettings):
    """Executor settings loaded from environment variables.

    All settings have sensible defaults for local development.
    Override via environment variables or .env file.
    """

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Redis Configuration
    redis_url: str = Field(
        default="redis://localhost:6379",
        description="Redis connection URL",
    )

    # Tools Configuration
    tools_path: str = Field(
        default=str(REPO_ROOT / "tools"),
        description="Path to tools directory",
    )

    # Schedule Mode Configuration
    schedule_mode: Literal["trigger", "cron", "speedrun"] = Field(
        default="trigger",
        description="Schedule mode: trigger (wait for requests), cron (time-based), or speedrun (continuous)",
    )

    # Speedrun Mode Configuration
    speedrun_interval: int = Field(
        default=5,
        ge=1,
        le=3600,
        description="Seconds between runs in speedrun mode (1-3600)",
    )
    speedrun_max_per_cycle: int = Field(
        default=3,
        ge=1,
        le=100,
        description="Maximum experiments to run per speedrun cycle (1-100)",
    )

    # Cron Mode Configuration
    cron_check_interval: int = Field(
        default=60,
        ge=10,
        le=3600,
        description="Seconds between schedule checks in cron mode (10-3600)",
    )

    # Execution Configuration
    tool_execution_timeout: int = Field(
        default=300,
        ge=1,
        le=3600,
        description="Timeout in seconds for tool execution (1-3600)",
    )

    # Retry Configuration
    retry_max_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum retry attempts for transient failures (1-10)",
    )
    retry_backoff_min: float = Field(
        default=1.0,
        ge=0.1,
        le=60.0,
        description="Minimum backoff delay in seconds (0.1-60)",
    )
    retry_backoff_max: float = Field(
        default=30.0,
        ge=1.0,
        le=300.0,
        description="Maximum backoff delay in seconds (1-300)",
    )

    # Redis Channels
    channel_schedules: str = Field(
        default="fullsend:schedules",
        description="Channel to subscribe for schedule updates",
    )
    channel_execute_now: str = Field(
        default="fullsend:execute_now",
        description="Channel to subscribe for trigger mode execution requests",
    )
    channel_metrics: str = Field(
        default="fullsend:metrics",
        description="Channel to publish metrics",
    )
    channel_experiment_results: str = Field(
        default="fullsend:experiment_results",
        description="Channel to publish experiment results",
    )

    @field_validator("schedule_mode")
    @classmethod
    def validate_schedule_mode(cls, v: str) -> str:
        """Validate schedule mode is one of the allowed values."""
        valid_modes = {"trigger", "cron", "speedrun"}
        if v not in valid_modes:
            raise ValueError(f"schedule_mode must be one of {valid_modes}, got '{v}'")
        return v

    @field_validator("retry_backoff_max")
    @classmethod
    def validate_backoff_max(cls, v: float, info) -> float:
        """Ensure backoff_max >= backoff_min."""
        if "retry_backoff_min" in info.data and v < info.data["retry_backoff_min"]:
            raise ValueError("retry_backoff_max must be >= retry_backoff_min")
        return v

    def get_mode_description(self) -> str:
        """Return a human-readable description of the current mode configuration."""
        if self.schedule_mode == "speedrun":
            return (
                f"Speedrun mode: Running experiments every {self.speedrun_interval}s, "
                f"max {self.speedrun_max_per_cycle} per cycle"
            )
        elif self.schedule_mode == "cron":
            return f"Cron mode: Checking schedules every {self.cron_check_interval}s"
        else:
            return f"Trigger mode: Listening on {self.channel_execute_now}"


def get_settings() -> Settings:
    """Create and return settings instance."""
    return Settings()
