from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import analytics, applications, emails, parse, settings, suggestions
from .config import settings as app_settings
from .db import SessionLocal, init_db
from .scheduler import shutdown as shutdown_scheduler
from .scheduler import start as start_scheduler
from .services.settings_service import get_poll_interval

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tracker")

# Resolve the built frontend directory relative to this file so it works
# regardless of where the process is launched from.
_HERE = Path(__file__).parent
STATIC_DIR = _HERE.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        interval = get_poll_interval(db, app_settings.email_poll_interval_seconds)
    finally:
        db.close()
    start_scheduler(interval)
    try:
        yield
    finally:
        shutdown_scheduler()


app = FastAPI(title="Job Application Tracker", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        app_settings.frontend_origin,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(applications.router)
app.include_router(analytics.router)
app.include_router(parse.router)
app.include_router(emails.router)
app.include_router(suggestions.router)
app.include_router(settings.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


# Serve the built React app if frontend/dist exists.
# In dev mode (npm run dev) this is skipped and Vite handles the frontend.
if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        """Return index.html for any non-API path so client-side routing works."""
        index = STATIC_DIR / "index.html"
        return FileResponse(str(index))
