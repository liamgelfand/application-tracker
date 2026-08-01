from __future__ import annotations

import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.security import decrypt
from ...models import LLMProvider

DEFAULT_OLLAMA_BASE = "http://localhost:11434"


class LLMError(Exception):
    """Raised when the LLM layer cannot fulfil a request."""


class LLMNotConfigured(LLMError):
    """Raised when no active LLM provider is configured."""


def get_active_provider(db: Session) -> LLMProvider | None:
    return db.execute(
        select(LLMProvider).where(LLMProvider.is_active.is_(True))
    ).scalar_one_or_none()


def _model_string(provider: LLMProvider) -> str:
    if "/" in provider.model:
        return provider.model
    return f"{provider.provider}/{provider.model}"


def _completion_kwargs(provider: LLMProvider) -> dict:
    kwargs: dict = {"model": _model_string(provider)}
    api_key = decrypt(provider.api_key_encrypted)
    if api_key:
        kwargs["api_key"] = api_key
    if provider.provider == "ollama":
        kwargs["api_base"] = provider.api_base or DEFAULT_OLLAMA_BASE
    elif provider.api_base:
        kwargs["api_base"] = provider.api_base
    return kwargs


def complete(db: Session, messages: list[dict], *, temperature: float = 0.0) -> str:
    """Run a chat completion against the active provider and return the text."""
    provider = get_active_provider(db)
    if provider is None:
        raise LLMNotConfigured(
            "No active LLM provider configured. Add one in Settings."
        )

    # Imported lazily so the app can boot even if litellm has heavy imports.
    import litellm

    kwargs = _completion_kwargs(provider)
    try:
        response = litellm.completion(
            messages=messages, temperature=temperature, **kwargs
        )
    except Exception as exc:  # noqa: BLE001 - surface a clean error to the API layer
        raise LLMError(f"LLM request failed: {exc}") from exc

    try:
        return response.choices[0].message.content or ""
    except (AttributeError, IndexError) as exc:
        raise LLMError("Unexpected response format from LLM provider.") from exc


def _extract_json(text: str) -> str:
    """Pull a JSON object out of an LLM response, tolerating code fences/prose."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)
    brace = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if brace:
        return brace.group(1)
    return text


def complete_json(db: Session, messages: list[dict], *, temperature: float = 0.0) -> dict:
    """Run a completion and parse the response as JSON."""
    raw = complete(db, messages, temperature=temperature)
    snippet = _extract_json(raw)
    try:
        return json.loads(snippet)
    except json.JSONDecodeError as exc:
        raise LLMError(f"Could not parse JSON from LLM response: {raw[:500]}") from exc
