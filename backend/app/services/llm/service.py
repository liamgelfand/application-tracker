from __future__ import annotations

import json
import logging
import os
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.security import decrypt
from ...models import LLMProvider

DEFAULT_OLLAMA_BASE = "http://localhost:11434"

# LiteLLM defaults to a 600s timeout. A single hung request would then stall an
# inbox sync for ten minutes per email with no way to recover, so cap it well
# below that. Local models are slower than hosted ones, hence the split.
ANALYSIS_TIMEOUT_S = 90
LOCAL_ANALYSIS_TIMEOUT_S = 180
CONNECTION_TEST_TIMEOUT_S = 30

_litellm_quieted = False


def _import_litellm():
    """Import litellm, turning any failure into an LLMError.

    A packaged build can be missing litellm's dynamically imported extras
    (tiktoken's encoding plugins), and a bare ImportError escaping this layer
    would kill the inbox sync thread instead of failing one email.
    """
    # Must be set before the first import: litellm otherwise downloads its
    # pricing map from GitHub at import time.
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    try:
        import litellm
    except Exception as exc:  # noqa: BLE001
        raise LLMError(
            f"The AI library failed to load ({exc}). This build may be "
            "missing a dependency — please report it."
        ) from exc
    return litellm


def _quiet_litellm() -> None:
    """LiteLLM prints each call twice (its own format + root logger). Mute the noise."""
    global _litellm_quieted
    if _litellm_quieted:
        return
    litellm = _import_litellm()

    litellm.suppress_debug_info = True
    litellm.set_verbose = False
    for name in ("LiteLLM", "litellm", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    _litellm_quieted = True


def _timeout_for(provider: str) -> int:
    return LOCAL_ANALYSIS_TIMEOUT_S if provider == "ollama" else ANALYSIS_TIMEOUT_S


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
    kwargs: dict = {
        "model": _model_string(provider),
        "timeout": _timeout_for(provider.provider),
    }
    api_key = decrypt(provider.api_key_encrypted)
    if api_key:
        kwargs["api_key"] = api_key
    if provider.provider == "ollama":
        kwargs["api_base"] = provider.api_base or DEFAULT_OLLAMA_BASE
    elif provider.api_base:
        kwargs["api_base"] = provider.api_base
    return kwargs


def _kwargs_from_fields(
    *,
    provider: str,
    model: str,
    api_key: str | None,
    api_base: str | None,
    timeout: int | None = None,
) -> dict:
    model_str = model if "/" in model else f"{provider}/{model}"
    kwargs: dict = {"model": model_str, "timeout": timeout or _timeout_for(provider)}
    if api_key:
        kwargs["api_key"] = api_key
    if provider == "ollama":
        kwargs["api_base"] = api_base or DEFAULT_OLLAMA_BASE
    elif api_base:
        kwargs["api_base"] = api_base
    return kwargs


def test_llm_connection(
    *,
    provider: str,
    model: str,
    api_key: str | None,
    api_base: str | None,
) -> tuple[bool, str]:
    """Send a tiny completion to verify provider + key + model."""
    try:
        litellm = _import_litellm()
        _quiet_litellm()
    except LLMError as exc:
        return False, str(exc)
    kwargs = _kwargs_from_fields(
        provider=provider,
        model=model,
        api_key=api_key,
        api_base=api_base,
        timeout=CONNECTION_TEST_TIMEOUT_S,
    )
    try:
        response = litellm.completion(
            messages=[{"role": "user", "content": "Reply with exactly: ok"}],
            temperature=0,
            max_tokens=8,
            **kwargs,
        )
        text = (response.choices[0].message.content or "").strip()
        return True, f"Connected — model responded: {text[:80] or '(empty)'}"
    except Exception as exc:  # noqa: BLE001
        return False, f"Failed: {exc}"


def complete(db: Session, messages: list[dict], *, temperature: float = 0.0) -> str:
    """Run a chat completion against the active provider and return the text."""
    provider = get_active_provider(db)
    if provider is None:
        raise LLMNotConfigured(
            "No active LLM provider configured. Add one in Settings."
        )

    # Capture connection kwargs while the session is live, then release the
    # SQLite lock before the (often slow) network call to the model.
    kwargs = _completion_kwargs(provider)
    try:
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()

    # Imported lazily so the app can boot even if litellm has heavy imports.
    litellm = _import_litellm()

    _quiet_litellm()
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
