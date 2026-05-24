from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
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
StreamTransport = Callable[[str, dict[str, str], dict[str, Any], float], Iterator[dict[str, Any]]]


@dataclass(frozen=True)
class ModelGatewayAuditEvent:
    provider: str
    model_alias: str
    model_name: str
    status: str
    usage: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0
    attempts: int = 0
    raw_id: str = ""
    failure_reason: str = ""


InvocationLogger = Callable[[ModelGatewayAuditEvent], None]


@dataclass(frozen=True)
class ModelGatewayResponse:
    provider: str
    model: str
    content: str
    usage: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0
    attempts: int = 1
    raw_id: str = ""


@dataclass(frozen=True)
class ModelGatewayStreamChunk:
    provider: str
    model: str
    content: str
    usage: dict[str, Any] = field(default_factory=dict)
    raw_id: str = ""
    done: bool = False


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


def resolve_model_gateway_api_base_url(settings: Settings) -> str:
    return (
        settings.model_gateway_api_base_url
        or os.getenv("QUALIFORGE_MODEL_GATEWAY_API_BASE_URL", "")
        or os.getenv("DEEPSEEK_BASE_URL", "")
        or _dotenv_value(("QUALIFORGE_MODEL_GATEWAY_API_BASE_URL", "DEEPSEEK_BASE_URL"))
        or "https://api.deepseek.com"
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


def urllib_stream_transport(
    url: str, headers: dict[str, str], payload: dict[str, Any], timeout_seconds: float
) -> Iterator[dict[str, Any]]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - configured model gateway URL.
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or line.startswith(":"):
                    continue
                data = line[5:].strip() if line.startswith("data:") else line
                if data == "[DONE]":
                    break
                try:
                    yield json.loads(data)
                except json.JSONDecodeError as exc:
                    raise NonRetryableModelGatewayError("Model gateway stream returned invalid JSON") from exc
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        if exc.code == 429 or exc.code >= 500:
            raise RetryableModelGatewayError(f"Model gateway transient HTTP {exc.code}: {detail}") from exc
        raise NonRetryableModelGatewayError(f"Model gateway HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RetryableModelGatewayError(f"Model gateway connection failed: {exc.reason}") from exc


class OpenAICompatibleModelGateway:
    def __init__(
        self,
        *,
        provider: str,
        api_base_url: str,
        api_key: str,
        default_model: str,
        default_reasoning_effort: str = "",
        timeout_seconds: int = 30,
        max_attempts: int = 3,
        transport: Transport = urllib_transport,
        stream_transport: StreamTransport = urllib_stream_transport,
    ):
        self.provider = provider
        self.api_base_url = api_base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = default_model
        self.default_reasoning_effort = default_reasoning_effort
        self.timeout_seconds = timeout_seconds
        self.max_attempts = min(max(1, max_attempts), 3)
        self.transport = transport
        self.stream_transport = stream_transport

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0,
        max_tokens: int = 256,
        reasoning_effort: str | None = None,
        invocation_logger: InvocationLogger | None = None,
    ) -> ModelGatewayResponse:
        selected_model = model or self.default_model
        started = time.monotonic()
        self._validate_config(selected_model, started=started, invocation_logger=invocation_logger)
        payload = self._chat_payload(
            messages,
            selected_model=selected_model,
            temperature=temperature,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
        )
        headers = self._headers()
        url = f"{self.api_base_url}/chat/completions"
        last_error: ModelGatewayError | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                raw = self.transport(url, headers, payload, float(self.timeout_seconds))
                choice = (raw.get("choices") or [{}])[0]
                message = choice.get("message") or {}
                content = str(message.get("content") or "")
                response = ModelGatewayResponse(
                    provider=self.provider,
                    model=str(raw.get("model") or selected_model),
                    content=content,
                    usage=dict(raw.get("usage") or {}),
                    latency_ms=int((time.monotonic() - started) * 1000),
                    attempts=attempt,
                    raw_id=str(raw.get("id") or ""),
                )
                self._emit_invocation(
                    invocation_logger,
                    model_alias=selected_model,
                    model_name=response.model,
                    status="succeeded",
                    usage=response.usage,
                    latency_ms=response.latency_ms,
                    attempts=response.attempts,
                    raw_id=response.raw_id,
                )
                return response
            except RetryableModelGatewayError as exc:
                last_error = exc
                if attempt == self.max_attempts:
                    break
                time.sleep(min(0.2 * attempt, 1.0))
            except NonRetryableModelGatewayError as exc:
                self._emit_invocation(
                    invocation_logger,
                    model_alias=selected_model,
                    model_name=selected_model,
                    status="failed",
                    latency_ms=int((time.monotonic() - started) * 1000),
                    attempts=attempt,
                    failure_reason=str(exc)[:500],
                )
                raise
        exc = RetryableModelGatewayError(f"Model gateway failed after {self.max_attempts} attempts: {last_error}")
        self._emit_invocation(
            invocation_logger,
            model_alias=selected_model,
            model_name=selected_model,
            status="failed",
            latency_ms=int((time.monotonic() - started) * 1000),
            attempts=self.max_attempts,
            failure_reason=str(exc)[:500],
        )
        raise exc

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0,
        max_tokens: int = 256,
        reasoning_effort: str | None = None,
        invocation_logger: InvocationLogger | None = None,
    ) -> Iterator[ModelGatewayStreamChunk]:
        selected_model = model or self.default_model
        started = time.monotonic()
        self._validate_config(selected_model, started=started, invocation_logger=invocation_logger)
        payload = self._chat_payload(
            messages,
            selected_model=selected_model,
            temperature=temperature,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
        )
        payload["stream"] = True
        headers = self._headers()
        url = f"{self.api_base_url}/chat/completions"
        usage: dict[str, Any] = {}
        raw_id = ""
        model_name = selected_model
        try:
            for raw in self.stream_transport(url, headers, payload, float(self.timeout_seconds)):
                raw_id = raw_id or str(raw.get("id") or "")
                model_name = str(raw.get("model") or model_name)
                usage.update(dict(raw.get("usage") or {}))
                choice = (raw.get("choices") or [{}])[0]
                delta = choice.get("delta") or choice.get("message") or {}
                content = str(delta.get("content") or "")
                if content:
                    yield ModelGatewayStreamChunk(
                        provider=self.provider,
                        model=model_name,
                        content=content,
                        usage=dict(usage),
                        raw_id=raw_id,
                    )
            self._emit_invocation(
                invocation_logger,
                model_alias=selected_model,
                model_name=model_name,
                status="succeeded",
                usage=usage,
                latency_ms=int((time.monotonic() - started) * 1000),
                attempts=1,
                raw_id=raw_id,
            )
            yield ModelGatewayStreamChunk(
                provider=self.provider,
                model=model_name,
                content="",
                usage=dict(usage),
                raw_id=raw_id,
                done=True,
            )
        except ModelGatewayError as exc:
            self._emit_invocation(
                invocation_logger,
                model_alias=selected_model,
                model_name=model_name,
                status="failed",
                latency_ms=int((time.monotonic() - started) * 1000),
                attempts=1,
                raw_id=raw_id,
                failure_reason=str(exc)[:500],
            )
            raise

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _chat_payload(
        self,
        messages: list[dict[str, str]],
        *,
        selected_model: str,
        temperature: float,
        max_tokens: int,
        reasoning_effort: str | None,
    ) -> dict[str, Any]:
        payload = {
            "model": selected_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        selected_reasoning_effort = reasoning_effort if reasoning_effort is not None else self.default_reasoning_effort
        if selected_reasoning_effort:
            payload["reasoning_effort"] = selected_reasoning_effort
        return payload

    def _validate_config(
        self,
        selected_model: str,
        *,
        started: float,
        invocation_logger: InvocationLogger | None,
    ) -> None:
        if not self.api_base_url:
            exc = NonRetryableModelGatewayError("Model gateway API base URL is not configured")
            self._emit_config_failure(selected_model, started=started, invocation_logger=invocation_logger, exc=exc)
            raise exc
        if not selected_model:
            exc = NonRetryableModelGatewayError("Model gateway model is not configured")
            self._emit_config_failure(selected_model, started=started, invocation_logger=invocation_logger, exc=exc)
            raise exc
        if not self.api_key:
            exc = NonRetryableModelGatewayError("Model gateway API key is not configured")
            self._emit_config_failure(selected_model, started=started, invocation_logger=invocation_logger, exc=exc)
            raise exc

    def _emit_config_failure(
        self,
        selected_model: str,
        *,
        started: float,
        invocation_logger: InvocationLogger | None,
        exc: ModelGatewayError,
    ) -> None:
        self._emit_invocation(
            invocation_logger,
            model_alias=selected_model,
            model_name=selected_model,
            status="failed",
            latency_ms=int((time.monotonic() - started) * 1000),
            attempts=0,
            failure_reason=str(exc),
        )

    def _emit_invocation(
        self,
        invocation_logger: InvocationLogger | None,
        *,
        model_alias: str,
        model_name: str,
        status: str,
        usage: dict[str, Any] | None = None,
        latency_ms: int,
        attempts: int,
        raw_id: str = "",
        failure_reason: str = "",
    ) -> None:
        if invocation_logger is None:
            return
        invocation_logger(
            ModelGatewayAuditEvent(
                provider=self.provider,
                model_alias=model_alias,
                model_name=model_name,
                status=status,
                usage=usage or {},
                latency_ms=latency_ms,
                attempts=attempts,
                raw_id=raw_id,
                failure_reason=failure_reason,
            )
        )


def build_model_gateway(settings: Settings, *, transport: Transport = urllib_transport) -> OpenAICompatibleModelGateway:
    return OpenAICompatibleModelGateway(
        provider=settings.model_gateway_provider,
        api_base_url=resolve_model_gateway_api_base_url(settings),
        api_key=resolve_model_gateway_api_key(settings),
        default_model=settings.model_gateway_default_model,
        default_reasoning_effort=settings.model_gateway_reasoning_effort,
        timeout_seconds=settings.model_gateway_timeout_seconds,
        max_attempts=settings.model_gateway_max_attempts,
        transport=transport,
    )
