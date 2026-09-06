"""Promote applied/phone_screen rows that actually received an online assessment.

Usually runs automatically on app startup. Re-run this script to force another pass:

    python -m scripts.backfill_online_assessments
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")
for candidate in (ROOT / "data", ROOT / "backend" / "data"):
    if (candidate / "tracker.db").exists():
        os.environ["DATA_DIR"] = str(candidate)
        break

from app.db import SessionLocal, init_db
from app.models import Application, ApplicationStatus
from app.services.oa_backfill import run_online_assessment_backfill


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        updated = run_online_assessment_backfill(db, force=True)
        if not updated:
            print("No applied/phone_screen rows needed an online-assessment backfill.")
            return
        print(f"Moved {updated} application(s) to online_assessment.")
        for app in (
            db.query(Application)
            .filter(Application.status == ApplicationStatus.online_assessment)
            .order_by(Application.id)
            .all()
        ):
            print(f"  #{app.id} {app.company} — {app.title}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
