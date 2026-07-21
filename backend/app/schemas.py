from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .models import (
    ApplicationStatus,
    EventSource,
    SuggestionKind,
    SuggestionStatus,
)


# ---------- Status events ----------
class StatusEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_status: ApplicationStatus | None = None
    to_status: ApplicationStatus | None = None
    note: str | None = None
    source: EventSource
    created_at: datetime


# ---------- Applications ----------
class ApplicationBase(BaseModel):
    company: str
    title: str
    location: str | None = None
    url: str | None = None
    source: str | None = None
    salary: str | None = None
    status: ApplicationStatus = ApplicationStatus.saved
    description: str | None = None
    skills: str | None = None
    notes: str | None = None
    contact_email: str | None = None
    date_applied: datetime | None = None


class ApplicationCreate(ApplicationBase):
    pass


class ApplicationUpdate(BaseModel):
    company: str | None = None
    title: str | None = None
    location: str | None = None
    url: str | None = None
    source: str | None = None
    salary: str | None = None
    status: ApplicationStatus | None = None
    description: str | None = None
    skills: str | None = None
    notes: str | None = None
    contact_email: str | None = None
    date_applied: datetime | None = None
    status_note: str | None = None  # optional note attached to a status change


class ApplicationOut(ApplicationBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class ApplicationDetailOut(ApplicationOut):
    events: list[StatusEventOut] = []


# ---------- Parsing ----------
class ParseRequest(BaseModel):
    text: str = Field(..., min_length=1)


class ParsedJob(BaseModel):
    company: str | None = None
    title: str | None = None
    location: str | None = None
    url: str | None = None
    salary: str | None = None
    source: str | None = None
    description: str | None = None
    skills: list[str] = []


# ---------- LLM providers ----------
class LLMProviderBase(BaseModel):
    name: str
    provider: str
    model: str
    api_base: str | None = None


class LLMProviderCreate(LLMProviderBase):
    api_key: str | None = None
    is_active: bool = False


class LLMProviderUpdate(BaseModel):
    name: str | None = None
    provider: str | None = None
    model: str | None = None
    api_base: str | None = None
    api_key: str | None = None  # send new key to replace; omit to keep existing
    is_active: bool | None = None


class LLMProviderOut(LLMProviderBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    has_api_key: bool = False
    created_at: datetime


# ---------- Email accounts ----------
class EmailAccountBase(BaseModel):
    name: str
    imap_host: str
    imap_port: int = 993
    username: str
    use_ssl: bool = True
    folder: str = "INBOX"
    active: bool = True


class EmailAccountCreate(EmailAccountBase):
    password: str


class EmailAccountUpdate(BaseModel):
    name: str | None = None
    imap_host: str | None = None
    imap_port: int | None = None
    username: str | None = None
    password: str | None = None
    use_ssl: bool | None = None
    folder: str | None = None
    active: bool | None = None


class EmailAccountOut(EmailAccountBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    last_synced_at: datetime | None = None
    created_at: datetime


class ConnectionTestRequest(BaseModel):
    imap_host: str
    imap_port: int = 993
    username: str
    password: str
    use_ssl: bool = True
    folder: str = "INBOX"


class ConnectionTestResult(BaseModel):
    ok: bool
    message: str


# ---------- Suggestions ----------
class SuggestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int | None = None
    kind: SuggestionKind
    status: SuggestionStatus
    suggested_status: ApplicationStatus | None = None
    summary: str | None = None
    confidence: int | None = None
    email_subject: str | None = None
    email_sender: str | None = None
    email_snippet: str | None = None
    created_at: datetime


# ---------- Misc ----------
class MessageOut(BaseModel):
    message: str


class SettingsOut(BaseModel):
    email_poll_interval_seconds: int
    auto_apply_suggestions: bool


class SettingsUpdate(BaseModel):
    auto_apply_suggestions: bool | None = None
    email_poll_interval_seconds: int | None = None
