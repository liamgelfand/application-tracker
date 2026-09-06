from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Application, ApplicationStatus, StatusEvent

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

RESPONDED = {
    ApplicationStatus.online_assessment,
    ApplicationStatus.phone_screen,
    ApplicationStatus.interview,
    ApplicationStatus.offer,
    ApplicationStatus.accepted,
    ApplicationStatus.rejected,
}
ADVANCED = {
    ApplicationStatus.phone_screen,
    ApplicationStatus.interview,
    ApplicationStatus.offer,
    ApplicationStatus.accepted,
}
CLOSED = {
    ApplicationStatus.rejected,
    ApplicationStatus.ghosted,
    ApplicationStatus.accepted,
}


def _pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(100 * numerator / denominator, 1)


@router.get("")
def get_analytics(db: Session = Depends(get_db)) -> dict:
    apps = db.execute(select(Application)).scalars().all()
    total = len(apps)

    by_status = Counter(a.status.value for a in apps)
    status_counts = {s.value: by_status.get(s.value, 0) for s in ApplicationStatus}

    # Denominator: applications actually submitted (exclude "saved" leads).
    submitted = [a for a in apps if a.status != ApplicationStatus.saved]
    submitted_count = len(submitted)

    responded = sum(1 for a in submitted if a.status in RESPONDED)
    advanced = sum(1 for a in submitted if a.status in ADVANCED)
    offers = sum(
        1
        for a in submitted
        if a.status in {ApplicationStatus.offer, ApplicationStatus.accepted}
    )

    active = sum(1 for a in apps if a.status not in CLOSED)

    # Average days from application creation to first "responded" status event.
    events = db.execute(
        select(StatusEvent).order_by(StatusEvent.created_at.asc())
    ).scalars().all()
    events_by_app: dict[int, list[StatusEvent]] = defaultdict(list)
    for ev in events:
        events_by_app[ev.application_id].append(ev)

    deltas: list[float] = []
    for a in apps:
        first_response = next(
            (
                ev
                for ev in events_by_app.get(a.id, [])
                if ev.to_status in RESPONDED
            ),
            None,
        )
        if first_response is not None:
            delta = (first_response.created_at - a.created_at).total_seconds() / 86400
            if delta >= 0:
                deltas.append(delta)
    avg_days_to_response = round(sum(deltas) / len(deltas), 1) if deltas else None

    # Applications submitted per week (last 8 weeks).
    today = date.today()
    start = today - timedelta(days=today.weekday())  # Monday of current week
    weeks = [start - timedelta(weeks=i) for i in range(7, -1, -1)]
    week_counts = {w.isoformat(): 0 for w in weeks}
    for a in apps:
        ref = a.date_applied or a.created_at
        if ref is None:
            continue
        d = ref.date()
        monday = d - timedelta(days=d.weekday())
        key = monday.isoformat()
        if key in week_counts:
            week_counts[key] += 1
    over_time = [{"week": k, "count": v} for k, v in week_counts.items()]

    return {
        "total": total,
        "submitted": submitted_count,
        "active": active,
        "status_counts": status_counts,
        "response_rate": _pct(responded, submitted_count),
        "interview_rate": _pct(advanced, submitted_count),
        "offer_rate": _pct(offers, submitted_count),
        "avg_days_to_response": avg_days_to_response,
        "over_time": over_time,
    }
