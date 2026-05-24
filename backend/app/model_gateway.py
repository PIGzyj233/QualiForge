from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import Settings


class ModelGatewayError(Exception):
    """Base error raised by model gateway calls."""


class RetryableModelGatewayError(ModelGatewayError):
    """Transient model gateway error that can be retried."""


class NonRetryableModelGatewayError(ModelGatewayError):
    """Permanent model gateway error that should fail fast."""


Transport = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]


@dataclass(frozen=True)
class ModelGatewayResponse:
    provider: str
    model: str
    content: str
    usage: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0
    attempts: int = 1
    raw_id: str = ""


def _dotenv_value(names: tuple[str, ...]) -> str:
    for candidate in (Path(".env"), Path("../.env")):
        if not candidate.exists():
            continue
        try:
            lines = candidate.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            if key.strip() in names:
                return value.strip().strip('"').strip("'")
    return ""


def resolve_model_gateway_api_key(settings: Settings) -> str:
    return (
        settings.model_gateway_api_key
        or os.getenv("QUALIFORGE_MODEL_GATEWAY_API_KEY", "")
        or os.getenv("DEEPSEEK_API_KEY", "")
        or _dotenv_value(("QUALIFORGE_MODEL_GATEWAY_API_KEY", "DEEPSEEK_API_KEY"))
    )


def urllib_transport(url: str, headers: dict[str, str], payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - configured model gateway URL.
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        if exc.code == 429 or exc.code >= 500:
            raise RetryableModelGatewayError(f"Model gateway transient HTTP {exc.code}: {detail}") from exc
        raise NonRetryableModelGatewayError(f"Model gateway HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RetryableModelGatewayError(f"Model gateway connection failed: {exc.reason}") from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise NonRetryableModelGatewayError("Model gateway returned invalid JSON") from exc


class OpenAICompatibleModelGateway:
    def __init__(
        self,
        *,
        provider: str,
        api_base_url: str,
        api_key: str,
        default_model: str,
        timeout_seconds: int = 30,
        max_attempts: int = 3,
        transport: Transport = urllib_transport,
    ):
        self.provider = provider
        self.api_base_url = api_base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = default_model
        self.timeout_seconds = timeout_seconds
        self.max_attempts = min(max(1, max_attempts), 3)
        self.transport = transport

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0,
        max_tokens: int = 256,
    ) -> ModelGatewayResponse:
        if not self.api_key:
            raise NonRetryableModelGatewayError("Model gateway API key is not configured")
        selected_model = model or self.default_model
        payload = {
            "model": selected_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.api_base_url}/chat/completions"
        started = time.monotonic()
        last_error: ModelGatewayError | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                raw = self.transport(url, headers, payload, float(self.timeout_seconds))
                choice = (raw.get("choices") or [{}])[0]
                message = choice.get("message") or {}
                content = str(message.get("content") or "")
                return ModelGatewayResponse(
                    provider=self.provider,
                    model=str(raw.get("model") or selected_model),
                    content=content,
                    usage=dict(raw.get("usage") or {}),
                    latency_ms=int((time.monotonic() - started) * 1000),
                    attempts=attempt,
                    raw_id=str(raw.get("id") or ""),
                )
            except RetryableModelGatewayError as exc:
                last_error = exc
                if attempt == self.max_attempts:
                    break
                time.sleep(min(0.2 * attempt, 1.0))
            except NonRetryableModelGatewayError:
                raise
        raise RetryableModelGatewayError(f"Model gateway failed after {self.max_attempts} attempts: {last_error}")


def build_model_gateway(settings: Settings, *, transport: Transport = urllib_transport) -> OpenAICompatibleModelGateway:
    return OpenAICompatibleModelGateway(
        provider=settings.model_gateway_provider,
        api_base_url=settings.model_gateway_api_base_url,
        api_key=resolve_model_gateway_api_key(settings),
        default_model=settings.model_gateway_default_model,
        timeout_seconds=settings.model_gateway_timeout_seconds,
        max_attempts=settings.model_gateway_max_attempts,
        transport=transport,
    )
