"""Configuration paths shared by the Specialist entry points."""

from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_settings() -> None:
    """Use environment overrides, then the project .env, then the repository .env."""
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(PROJECT_ROOT.parent / ".env")
