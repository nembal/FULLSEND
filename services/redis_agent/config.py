"""Configuration for Redis Agent using Pydantic settings."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Get the repo root (two levels up from this file)
REPO_ROOT = Path(__file__).parent.parent.parent
ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    """Redis Agent configuration."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379",
        description="Redis connection URL",
    )

    # Gemini
    google_api_key: str = Field(
        default="",
        description="Google API key for Gemini",
    )
    redis_agent_model: str = Field(
        default="gemini-2.0-flash-exp",
        description="Gemini model to use",
    )

    # Alert cooldown (seconds) - prevent alert spam
    alert_cooldown_seconds: int = Field(
        default=300,
        description="Cooldown between alerts in seconds",
    )

    # Summary interval (seconds) - hourly by default
    summary_interval_seconds: int = Field(
        default=3600,
        description="Interval between summaries in seconds",
    )

    # Threshold check interval (seconds)
    threshold_check_interval_seconds: int = Field(
        default=60,
        description="Interval between threshold checks in seconds",
    )

    # Redis channels
    metrics_channel: str = Field(
        default="fullsend:metrics",
        description="Redis channel for metrics",
    )
    orchestrator_channel: str = Field(
        default="fullsend:to_orchestrator",
        description="Redis channel for orchestrator",
    )


def get_settings() -> Settings:
    """Create and return settings instance."""
    return Settings()
