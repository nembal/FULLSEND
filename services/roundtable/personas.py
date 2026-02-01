"""System prompts for ARTIST, BUSINESS, TECH, SUMMARIZER. Loaded from .txt files."""

from pathlib import Path

ROLES = ("artist", "business", "tech")

PERSONAS_DIR = Path(__file__).parent / "personas"


def load_persona(name: str) -> str:
    """Load persona prompt from .txt file."""
    filepath = PERSONAS_DIR / f"{name}.txt"
    if not filepath.exists():
        raise FileNotFoundError(f"Persona file not found: {filepath}")
    return filepath.read_text().strip()


def get_persona(role: str) -> str:
    """Return system prompt for role (artist, business, tech)."""
    r = role.lower()
    if r not in ROLES:
        raise ValueError(f"Unknown role: {role}. Use one of {ROLES}")
    return load_persona(r)


def get_summarizer_prompt() -> str:
    """Return the summarizer persona prompt."""
    return load_persona("summarizer")
