"""Configuration module using Pydantic Settings."""

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Get the repo root (two levels up from this file)
REPO_ROOT = Path(__file__).parent.parent.parent
ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Discord Configuration
    discord_token: str = Field(..., description="Discord bot token")
    discord_guild_id: str = Field(..., description="Discord guild/server ID")

    # Channel Configuration
    listening_channels: str = Field(
        default="ideas,gtm,brainstorm",
        description="Comma-separated list of channel names to listen to",
    )
    status_channel: str = Field(
        default="fullsend-status",
        description="Channel name for status updates",
    )
    idea_react_emoji: str = Field(
        default="🎯",
        description="Emoji to react with when an idea is detected",
    )

    # Redis Configuration
    redis_url: str = Field(
        default="redis://localhost:6379",
        description="Redis connection URL",
    )

    # Environment Mode
    env: Literal["discord", "web", "both"] = Field(
        default="both",
        description="Which adapters to run: discord, web, or both",
    )

    # Web Server Configuration
    web_port: int = Field(
        default=8000,
        description="Port for the web server",
    )

    @field_validator("discord_token")
    @classmethod
    def validate_discord_token(cls, v: str) -> str:
        """Validate that discord token is not a placeholder."""
        if not v or v == "your_discord_bot_token_here":
            raise ValueError("DISCORD_TOKEN must be set to a valid token")
        return v

    @field_validator("discord_guild_id")
    @classmethod
    def validate_discord_guild_id(cls, v: str) -> str:
        """Validate that guild ID is not a placeholder."""
        if not v or v == "your_guild_id_here":
            raise ValueError("DISCORD_GUILD_ID must be set to a valid ID")
        return v

    @property
    def listening_channels_list(self) -> list[str]:
        """Return listening channels as a list."""
        return [ch.strip() for ch in self.listening_channels.split(",") if ch.strip()]

    @property
    def should_run_discord(self) -> bool:
        """Check if Discord adapter should run."""
        return self.env in ("discord", "both")

    @property
    def should_run_web(self) -> bool:
        """Check if Web adapter should run."""
        return self.env in ("web", "both")


def get_settings() -> Settings:
    """Create and return settings instance."""
    return Settings()
