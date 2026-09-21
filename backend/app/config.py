from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = "AppTracker"

# Repo-relative locations used before the app stored data per-user. A packaged
# build must not write next to the executable, and a cloud-synced checkout
# corrupts SQLite WAL files, so these are migrated once and left in place.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_LEGACY_DATA_DIRS = (
    _PROJECT_ROOT / "data",
    _PROJECT_ROOT / "backend" / "data",
)
_MIGRATED_FILES = (
    "tracker.db",
    "tracker.db-wal",
    "tracker.db-shm",
    "secret.key",
)

_migration_checked = False


def default_data_dir() -> Path:
    """Per-user writable location for the database and encryption key."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / APP_NAME


def _migrate_legacy_data(target: Path) -> None:
    """Copy a repo-local database into the per-user directory, once.

    Copies rather than moves so an older build pointed at the old path still
    starts, and never overwrites a database that already exists at the target.
    """
    global _migration_checked
    if _migration_checked:
        return
    _migration_checked = True
    if (target / "tracker.db").exists():
        return
    for legacy in _LEGACY_DATA_DIRS:
        try:
            if legacy.resolve() == target.resolve():
                continue
        except OSError:
            continue
        if not (legacy / "tracker.db").exists():
            continue
        target.mkdir(parents=True, exist_ok=True)
        for name in _MIGRATED_FILES:
            source = legacy / name
            if source.exists():
                shutil.copy2(source, target / name)
        (target / "MIGRATED_FROM.txt").write_text(
            f"Copied from {legacy}\n", encoding="utf-8"
        )
        return


class Settings(BaseSettings):
    """Application configuration loaded from environment / .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Unset means "use the per-user app data directory".
    data_dir: str | None = None
    frontend_origin: str = "http://localhost:5173"
    email_poll_interval_seconds: int = 900
    app_secret_key: str | None = None

    @property
    def data_path(self) -> Path:
        if self.data_dir:
            path = Path(self.data_dir).resolve()
            path.mkdir(parents=True, exist_ok=True)
            return path
        path = default_data_dir()
        _migrate_legacy_data(path)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.data_path / 'tracker.db'}"

    @property
    def secret_key_file(self) -> Path:
        return self.data_path / "secret.key"


settings = Settings()
