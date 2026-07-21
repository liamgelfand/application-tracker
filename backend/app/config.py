from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment / .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: str = "./data"
    frontend_origin: str = "http://localhost:5173"
    email_poll_interval_seconds: int = 900
    app_secret_key: str | None = None

    @property
    def data_path(self) -> Path:
        path = Path(self.data_dir).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.data_path / 'tracker.db'}"

    @property
    def secret_key_file(self) -> Path:
        return self.data_path / "secret.key"


settings = Settings()
