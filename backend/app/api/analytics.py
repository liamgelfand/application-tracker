from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Application, ApplicationStatus, EventSource, StatusEvent
from ..services.status_inference import (
    looks_like_live_interview,
    looks_like_online_assessment,
)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

RESPONDED = {
    ApplicationStatus.online_assessment,
    ApplicationStatus.phone_screen,
    ApplicationStatus.interview,
    ApplicationStatus.offer,
    ApplicationStatus.accepted,
    ApplicationStatus.rejected,
}
# Live interview loop — not OA / HireVue / coding tests, and not a recruiter screen.
INTERVIEWS = {
    ApplicationStatus.interview,
    ApplicationStatus.offer,
    ApplicationStatus.accepted,
}
ASSESSMENTS = {ApplicationStatus.online_assessment}
OFFERS = {ApplicationStatus.offer, ApplicationStatus.accepted}
CLOSED = {
    ApplicationStatus.rejected,
    ApplicationStatus.ghosted,
    ApplicationStatus.accepted,
}

# Pipeline rank for "highest stage reached" (closed outcomes excluded).
STAGE_RANK = {
    ApplicationStatus.applied: 1,
    ApplicationStatus.online_assessment: 2,
    ApplicationStatus.phone_screen: 3,
    ApplicationStatus.interview: 4,
    ApplicationStatus.offer: 5,
    ApplicationStatus.accepted: 6,
}

REJECTION_STAGES = [
    ApplicationStatus.applied,
    ApplicationStatus.online_assessment,
    ApplicationStatus.phone_screen,
    ApplicationStatus.interview,
    ApplicationStatus.offer,
]


def _pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(100 * numerator / denominator, 1)


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def _effective_to_status(event: StatusEvent) -> ApplicationStatus | None:
    """Map a timeline event to the stage it actually represents.

    Older email syncs labeled coding tests / HireVue / digital screens as
    phone_screen or interview. Prefer the note over that label so OA does
    not inflate interview rate. A real live-interview note keeps interview.
    """
    status = event.to_status
    if status is None:
        return None
    note = event.note or ""
    if status in {
        ApplicationStatus.phone_screen,
        ApplicationStatus.interview,
    }:
        if looks_like_online_assessment(note) and not looks_like_live_interview(note):
            return ApplicationStatus.online_assessment
    # Email sync often stamped "interview" on OA invites and confirmations.
    # Only count those as a live interview when the note actually says so.
    if (
        status == ApplicationStatus.interview
        and event.source == EventSource.email
        and not looks_like_live_interview(note)
    ):
        if looks_like_online_assessment(note):
            return ApplicationStatus.online_assessment
        return ApplicationStatus.applied
    return status


def _statuses_ever(
    app: Application, events: list[StatusEvent]
) -> set[ApplicationStatus]:
    found: set[ApplicationStatus] = set()
    for ev in events:
        status = _effective_to_status(ev)
        if status is not None:
            found.add(status)
    # Current phone_screen / interview can be a mislabeled OA; trust events.
    if app.status is not None and app.status not in {
        ApplicationStatus.phone_screen,
        ApplicationStatus.interview,
    }:
        found.add(app.status)
    return found


def _highest_stage(statuses: set[ApplicationStatus]) -> ApplicationStatus | None:
    best: ApplicationStatus | None = None
    best_rank = 0
    for status in statuses:
        rank = STAGE_RANK.get(status, 0)
        if rank > best_rank:
            best_rank = rank
            best = status
    return best


def _days_to_first(
    app: Application,
    events: list[StatusEvent],
    targets: set[ApplicationStatus],
) -> float | None:
    first = next(
        (ev for ev in events if _effective_to_status(ev) in targets),
        None,
    )
    if first is None:
        return None
    delta = (first.created_at - app.created_at).total_seconds() / 86400
    if delta < 0:
        return None
    return delta


def _blank_label(value: str | None) -> str:
    if value is None:
        return "Unknown"
    stripped = value.strip()
    return stripped or "Unknown"


@router.get("")
def get_analytics(db: Session = Depends(get_db)) -> dict:
    apps = db.execute(select(Application)).scalars().all()
    total = len(apps)

    by_status = Counter(a.status.value for a in apps)
    status_counts = {s.value: by_status.get(s.value, 0) for s in ApplicationStatus}

    # Denominator: applications actually submitted (exclude current "saved" leads).
    submitted = [a for a in apps if a.status != ApplicationStatus.saved]
    submitted_count = len(submitted)
    active = sum(1 for a in apps if a.status not in CLOSED)
    ghosted_count = sum(1 for a in submitted if a.status == ApplicationStatus.ghosted)

    events = (
        db.execute(select(StatusEvent).order_by(StatusEvent.created_at.asc()))
        .scalars()
        .all()
    )
    events_by_app: dict[int, list[StatusEvent]] = defaultdict(list)
    for ev in events:
        events_by_app[ev.application_id].append(ev)

    # Rate metrics use the full status timeline so interview → rejected still
    # counts as an interview (and similarly for responses / offers).
    ever_by_app = {
        a.id: _statuses_ever(a, events_by_app.get(a.id, [])) for a in apps
    }

    responded = sum(1 for a in submitted if ever_by_app[a.id] & RESPONDED)
    assessed = sum(1 for a in submitted if ever_by_app[a.id] & ASSESSMENTS)
    interviewed = sum(1 for a in submitted if ever_by_app[a.id] & INTERVIEWS)
    offers = sum(1 for a in submitted if ever_by_app[a.id] & OFFERS)

    response_deltas: list[float] = []
    oa_deltas: list[float] = []
    interview_deltas: list[float] = []
    offer_deltas: list[float] = []
    for a in apps:
        evs = events_by_app.get(a.id, [])
        days = _days_to_first(a, evs, RESPONDED)
        if days is not None:
            response_deltas.append(days)
        days = _days_to_first(a, evs, ASSESSMENTS)
        if days is not None:
            oa_deltas.append(days)
        days = _days_to_first(a, evs, INTERVIEWS)
        if days is not None:
            interview_deltas.append(days)
        days = _days_to_first(a, evs, OFFERS)
        if days is not None:
            offer_deltas.append(days)

    funnel = [
        {
            "stage": "submitted",
            "label": "Submitted",
            "count": submitted_count,
            "rate": 100.0 if submitted_count else 0.0,
            "conversion": None,
        },
        {
            "stage": "responded",
            "label": "Heard back",
            "count": responded,
            "rate": _pct(responded, submitted_count),
            "conversion": _pct(responded, submitted_count),
        },
        {
            "stage": "online_assessment",
            "label": "Online assessment",
            "count": assessed,
            "rate": _pct(assessed, submitted_count),
            "conversion": _pct(assessed, responded),
        },
        {
            "stage": "interview",
            "label": "Interview",
            "count": interviewed,
            "rate": _pct(interviewed, submitted_count),
            "conversion": _pct(interviewed, assessed) if assessed else _pct(interviewed, responded),
        },
        {
            "stage": "offer",
            "label": "Offer",
            "count": offers,
            "rate": _pct(offers, submitted_count),
            "conversion": _pct(offers, interviewed),
        },
    ]

    rejection_counts = {s.value: 0 for s in REJECTION_STAGES}
    for a in submitted:
        if a.status != ApplicationStatus.rejected:
            continue
        prior = ever_by_app[a.id] - {
            ApplicationStatus.rejected,
            ApplicationStatus.ghosted,
        }
        highest = _highest_stage(prior) or ApplicationStatus.applied
        if highest == ApplicationStatus.accepted:
            highest = ApplicationStatus.offer
        rejection_counts[highest.value] = rejection_counts.get(highest.value, 0) + 1
    rejection_by_stage = [
        {"stage": stage.value, "count": rejection_counts[stage.value]}
        for stage in REJECTION_STAGES
    ]

    source_groups: dict[str, list[Application]] = defaultdict(list)
    company_groups: dict[str, list[Application]] = defaultdict(list)
    for a in submitted:
        source_groups[_blank_label(a.source)].append(a)
        company_groups[_blank_label(a.company)].append(a)

    def _group_stats(label: str, group: list[Application], key_name: str) -> dict:
        n = len(group)
        heard = sum(1 for a in group if ever_by_app[a.id] & RESPONDED)
        oa = sum(1 for a in group if ever_by_app[a.id] & ASSESSMENTS)
        interviewed_n = sum(1 for a in group if ever_by_app[a.id] & INTERVIEWS)
        offered = sum(1 for a in group if ever_by_app[a.id] & OFFERS)
        return {
            key_name: label,
            "submitted": n,
            "response_rate": _pct(heard, n),
            "oa_rate": _pct(oa, n),
            "interview_rate": _pct(interviewed_n, n),
            "offer_rate": _pct(offered, n),
            "assessments": oa,
            "interviews": interviewed_n,
            "offers": offered,
        }

    by_source = sorted(
        (
            _group_stats(label, group, "source")
            for label, group in source_groups.items()
        ),
        key=lambda row: (-row["submitted"], row["source"]),
    )
    by_company = sorted(
        (
            _group_stats(label, group, "company")
            for label, group in company_groups.items()
        ),
        key=lambda row: (
            -row["submitted"],
            -row["interviews"],
            -row["assessments"],
            row["company"],
        ),
    )[:10]

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
        "response_count": responded,
        "oa_count": assessed,
        "interview_count": interviewed,
        "offer_count": offers,
        "ghost_count": ghosted_count,
        "response_rate": _pct(responded, submitted_count),
        "oa_rate": _pct(assessed, submitted_count),
        "interview_rate": _pct(interviewed, submitted_count),
        "offer_rate": _pct(offers, submitted_count),
        "ghost_rate": _pct(ghosted_count, submitted_count),
        "avg_days_to_response": _avg(response_deltas),
        "avg_days_to_oa": _avg(oa_deltas),
        "avg_days_to_interview": _avg(interview_deltas),
        "avg_days_to_offer": _avg(offer_deltas),
        "funnel": funnel,
        "rejection_by_stage": rejection_by_stage,
        "by_source": by_source,
        "by_company": by_company,
        "over_time": over_time,
    }
