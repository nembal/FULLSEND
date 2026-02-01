"""Configuration module for Watcher service using Pydantic Settings."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Get the repo root (two levels up from this file)
REPO_ROOT = Path(__file__).parent.parent.parent
ENV_FILE = REPO_ROOT / ".env"
PROMPTS_DIR = Path(__file__).parent / "prompts"


class Settings(BaseSettings):
    """Watcher settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Google Gemini API Configuration
    google_api_key: str = Field(..., description="Google API key for Gemini")
    watcher_model: str = Field(
        default="gemini-2.0-flash-exp",
        description="Gemini model to use for classification",
    )

    # Redis Configuration
    redis_url: str = Field(
        default="redis://localhost:6379",
        description="Redis connection URL",
    )

    # Redis Channels
    channel_discord_raw: str = Field(
        default="fullsend:discord_raw",
        description="Channel to subscribe for raw Discord messages",
    )
    channel_to_orchestrator: str = Field(
        default="fullsend:to_orchestrator",
        description="Channel to publish escalations",
    )
    channel_from_orchestrator: str = Field(
        default="fullsend:from_orchestrator",
        description="Channel to publish simple responses",
    )

    # Classification Settings
    classification_temperature: float = Field(
        default=0.1,
        description="Temperature for classification (low for consistency)",
    )
    classification_max_tokens: int = Field(
        default=500,
        description="Max output tokens for classification",
    )

    # Response Generation Settings
    response_temperature: float = Field(
        default=0.3,
        description="Temperature for response generation (slightly higher for natural responses)",
    )
    response_max_tokens: int = Field(
        default=200,
        description="Max output tokens for responses (keep brief)",
    )

    # Retry Settings for Model Calls
    model_retry_attempts: int = Field(
        default=3,
        description="Number of retry attempts for model calls",
    )
    model_retry_base_delay: float = Field(
        default=1.0,
        description="Base delay in seconds between retries (exponential backoff)",
    )
    model_retry_max_delay: float = Field(
        default=10.0,
        description="Maximum delay in seconds between retries",
    )


def get_settings() -> Settings:
    """Create and return settings instance."""
    return Settings()
