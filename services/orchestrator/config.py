"""Configuration module for Orchestrator service using Pydantic Settings."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Get the repo root (two levels up from this file)
REPO_ROOT = Path(__file__).parent.parent.parent
ENV_FILE = REPO_ROOT / ".env"
PROMPTS_DIR = Path(__file__).parent / "prompts"


class Settings(BaseSettings):
    """Orchestrator settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Anthropic API Configuration
    anthropic_api_key: str = Field(..., description="Anthropic API key for Claude")
    orchestrator_model: str = Field(
        default="claude-opus-4-20250514",
        description="Claude model to use for strategic decisions",
    )
    orchestrator_thinking_budget: int = Field(
        default=10000,
        description="Token budget for extended thinking",
    )
    orchestrator_max_tokens: int = Field(
        default=16000,
        description="Max output tokens for model responses",
    )

    # Redis Configuration
    redis_url: str = Field(
        default="redis://localhost:6379",
        description="Redis connection URL",
    )

    # Redis Channels - Subscribe
    channel_to_orchestrator: str = Field(
        default="fullsend:to_orchestrator",
        description="Channel to receive escalations and alerts",
    )

    # Redis Channels - Publish
    channel_from_orchestrator: str = Field(
        default="fullsend:from_orchestrator",
        description="Channel to publish responses to Discord",
    )
    channel_to_fullsend: str = Field(
        default="fullsend:to_fullsend",
        description="Channel to publish experiment requests",
    )
    channel_builder_tasks: str = Field(
        default="fullsend:builder_tasks",
        description="Channel to publish tool PRDs to Builder",
    )

    # Context File Paths
    context_path: Path = Field(
        default=Path("/app/context"),
        description="Base path for context files",
    )

    # Timeout Settings
    thinking_timeout_seconds: int = Field(
        default=60,
        description="Timeout for extended thinking model calls",
    )

    # Roundtable Settings
    roundtable_timeout_seconds: int = Field(
        default=120,
        description="Timeout for Roundtable subprocess calls",
    )
    roundtable_max_rounds: int = Field(
        default=3,
        description="Number of rounds for Roundtable debate",
    )


def get_settings() -> Settings:
    """Create and return settings instance."""
    return Settings()
