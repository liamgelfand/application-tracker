"""Seed the database with realistic demo data.

Useful for taking screenshots or trying the UI without connecting a real inbox.

Usage (from the backend/ directory, with the venv active):
    python -m scripts.seed_demo

This ADDS demo rows; it does not delete your existing data. Pass --reset to
wipe all applications/suggestions first.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from app.db import SessionLocal, init_db
from app.models import (
    Application,
    ApplicationStatus,
    EventSource,
    StatusEvent,
    Suggestion,
    SuggestionKind,
    SuggestionStatus,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


DEMO_APPS = [
    dict(
        company="Vercel",
        title="Senior Frontend Engineer",
        location="Remote (US)",
        salary="$180k-$220k",
        source="LinkedIn",
        status=ApplicationStatus.interview,
        skills="React, TypeScript, Next.js, Edge functions",
        description="Build the framework and tools used by millions of developers.",
    ),
    dict(
        company="Stripe",
        title="Backend Engineer, Payments",
        location="Seattle, WA",
        salary="$190k-$240k",
        source="Referral",
        status=ApplicationStatus.phone_screen,
        skills="Python, Go, distributed systems",
        description="Work on the APIs that move money for the internet economy.",
    ),
    dict(
        company="Notion",
        title="Full-Stack Engineer",
        location="New York, NY",
        salary="$170k-$210k",
        source="Company site",
        status=ApplicationStatus.applied,
        skills="React, Node.js, PostgreSQL",
        description="Help build the connected workspace for docs, wikis, and projects.",
    ),
    dict(
        company="Linear",
        title="Product Engineer",
        location="Remote",
        salary="$160k-$200k",
        source="Twitter",
        status=ApplicationStatus.offer,
        skills="TypeScript, React, GraphQL",
        description="Craft the issue tracker that high-performing teams love.",
    ),
    dict(
        company="Datadog",
        title="Software Engineer, Observability",
        location="Boston, MA",
        salary="$175k-$215k",
        source="Indeed",
        status=ApplicationStatus.rejected,
        skills="Go, Kafka, time-series databases",
        description="Scale the monitoring platform used by tens of thousands of companies.",
    ),
    dict(
        company="Figma",
        title="Frontend Engineer, Design Systems",
        location="San Francisco, CA",
        salary="$185k-$225k",
        source="LinkedIn",
        status=ApplicationStatus.saved,
        skills="React, WebGL, TypeScript",
        description="Build the collaborative design tool used by product teams everywhere.",
    ),
    dict(
        company="Ramp",
        title="Software Engineer",
        location="New York, NY",
        salary="$165k-$205k",
        source="Company site",
        status=ApplicationStatus.ghosted,
        skills="TypeScript, React, Node.js",
        description="Build finance automation that saves companies time and money.",
    ),
]


def reset(db) -> None:
    db.query(StatusEvent).delete()
    db.query(Suggestion).delete()
    db.query(Application).delete()
    db.commit()


def seed(db) -> None:
    created: list[Application] = []
    for i, data in enumerate(DEMO_APPS):
        app = Application(
            **data,
            date_applied=_now() - timedelta(days=3 * i + 2),
            created_at=_now() - timedelta(days=3 * i + 2),
        )
        db.add(app)
        db.flush()
        db.add(
            StatusEvent(
                application_id=app.id,
                from_status=None,
                to_status=ApplicationStatus.applied,
                note="Application submitted",
                source=EventSource.manual,
                created_at=_now() - timedelta(days=3 * i + 2),
            )
        )
        if app.status not in (ApplicationStatus.saved, ApplicationStatus.applied):
            db.add(
                StatusEvent(
                    application_id=app.id,
                    from_status=ApplicationStatus.applied,
                    to_status=app.status,
                    note="Detected from email",
                    source=EventSource.email,
                    created_at=_now() - timedelta(days=i),
                )
            )
        created.append(app)

    # A couple of pending suggestions for the review queue.
    db.add(
        Suggestion(
            application_id=created[2].id,
            kind=SuggestionKind.status_change,
            status=SuggestionStatus.pending,
            suggested_status=ApplicationStatus.phone_screen,
            summary="Notion recruiter wants to schedule an intro call.",
            confidence=88,
            email_subject="Next steps for your Notion application",
            email_sender="recruiting@notion.so",
            email_snippet="Hi! We loved your application and would like to set up a "
            "30-minute intro call this week. Are you available Thursday?",
        )
    )
    db.add(
        Suggestion(
            kind=SuggestionKind.new_application,
            status=SuggestionStatus.pending,
            suggested_status=ApplicationStatus.applied,
            summary="Application confirmation from Airbnb for a role you haven't logged.",
            confidence=76,
            payload='{"company": "Airbnb", "title": "Software Engineer"}',
            email_subject="We received your application, thank you!",
            email_sender="no-reply@airbnb.com",
            email_snippet="Thanks for applying to the Software Engineer role at Airbnb. "
            "Our team will review your application and be in touch.",
        )
    )
    db.commit()
    print(f"Seeded {len(created)} applications and 2 pending suggestions.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo data.")
    parser.add_argument(
        "--reset", action="store_true", help="Delete existing data first."
    )
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        if args.reset:
            reset(db)
            print("Cleared existing applications, suggestions, and events.")
        seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
