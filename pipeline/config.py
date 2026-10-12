"""Reads settings from the .env file (or real environment variables).

Real environment variables win over values in .env, so a setting can be
overridden for one run without editing the file.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"
PLACEHOLDER_KEY = "your_key_here"


@dataclass(frozen=True)
class Settings:
    # repr=False keeps secrets out of logs and error messages.
    nasa_api_key: str = field(repr=False)
    db_host: str
    db_port: int
    db_socket: str
    db_user: str
    db_password: str = field(repr=False)
    db_name: str

    @property
    def has_real_api_key(self) -> bool:
        return bool(self.nasa_api_key) and self.nasa_api_key != PLACEHOLDER_KEY


def load_settings(env_file: Path | None = None) -> Settings:
    file_values = dotenv_values(env_file or DEFAULT_ENV_FILE)

    def get(name: str, default: str = "") -> str:
        return os.environ.get(name, file_values.get(name) or default)

    return Settings(
        nasa_api_key=get("NASA_API_KEY"),
        db_host=get("DB_HOST", "127.0.0.1"),
        db_port=int(get("DB_PORT", "3306")),
        db_socket=get("DB_SOCKET"),
        db_user=get("DB_USER", "asteroid_user"),
        db_password=get("DB_PASSWORD"),
        db_name=get("DB_NAME", "asteroid_watch"),
    )
