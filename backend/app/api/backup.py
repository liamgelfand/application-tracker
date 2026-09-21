"""Download and restore the whole local dataset as a single zip.

The encryption key lives alongside the database and cannot be regenerated: if
it is lost, every stored API key and mailbox password becomes unreadable. Both
files therefore travel together.
"""
from __future__ import annotations

import io
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from ..config import settings
from ..db import engine, init_db
from ..schemas import MessageOut

router = APIRouter(prefix="/api/backup", tags=["backup"])

DB_NAME = "tracker.db"
KEY_NAME = "secret.key"
_MAX_UPLOAD_BYTES = 200 * 1024 * 1024


def _snapshot_database(destination: Path) -> None:
    """Consistent copy even with WAL journaling and an active sync in flight."""
    source = sqlite3.connect(str(settings.data_path / DB_NAME))
    try:
        target = sqlite3.connect(str(destination))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


@router.get("")
def download_backup() -> Response:
    with tempfile.TemporaryDirectory() as tmp:
        db_copy = Path(tmp) / DB_NAME
        _snapshot_database(db_copy)

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(db_copy, DB_NAME)
            key_file = settings.secret_key_file
            if key_file.exists():
                archive.write(key_file, KEY_NAME)
            archive.writestr(
                "README.txt",
                "AppTracker backup\n\n"
                f"Created: {datetime.now(timezone.utc).isoformat()}\n"
                f"{DB_NAME}  your applications, emails and settings\n"
                f"{KEY_NAME}  decrypts stored API keys and mailbox passwords\n\n"
                "Restore from Settings -> Backup. Keep this file private.\n",
            )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="apptracker-backup-{stamp}.zip"'
        },
    )


@router.post("/restore", response_model=MessageOut)
async def restore_backup(file: UploadFile = File(...)) -> MessageOut:
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Backup file is empty")
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Backup file is too large")

    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=400, detail="Not a valid AppTracker backup (.zip expected)"
        ) from None

    names = set(archive.namelist())
    if DB_NAME not in names:
        raise HTTPException(
            status_code=400, detail=f"Backup is missing {DB_NAME}"
        )

    data_dir = settings.data_path
    with tempfile.TemporaryDirectory() as tmp:
        staged_db = Path(tmp) / DB_NAME
        staged_db.write_bytes(archive.read(DB_NAME))

        # Reject a corrupt or unrelated database before touching live data.
        try:
            probe = sqlite3.connect(str(staged_db))
            try:
                tables = {
                    row[0]
                    for row in probe.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
            finally:
                probe.close()
        except sqlite3.DatabaseError:
            raise HTTPException(
                status_code=400, detail="Backup database is unreadable"
            ) from None
        if "applications" not in tables:
            raise HTTPException(
                status_code=400, detail="Backup does not look like AppTracker data"
            )

        staged_key = None
        if KEY_NAME in names:
            staged_key = Path(tmp) / KEY_NAME
            staged_key.write_bytes(archive.read(KEY_NAME))

        # Keep the current dataset recoverable if the swap goes wrong.
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        rollback = data_dir / f"pre-restore-{stamp}"
        rollback.mkdir(parents=True, exist_ok=True)
        engine.dispose()
        for name in (DB_NAME, f"{DB_NAME}-wal", f"{DB_NAME}-shm", KEY_NAME):
            existing = data_dir / name
            if existing.exists():
                shutil.move(str(existing), str(rollback / name))

        shutil.copy2(staged_db, data_dir / DB_NAME)
        if staged_key is not None:
            shutil.copy2(staged_key, data_dir / KEY_NAME)
        elif (rollback / KEY_NAME).exists():
            # No key in the archive: the existing one is the best chance of
            # still decrypting saved credentials.
            shutil.copy2(rollback / KEY_NAME, data_dir / KEY_NAME)

    init_db()
    return MessageOut(
        message="Backup restored. Restart AppTracker to finish loading it."
    )
