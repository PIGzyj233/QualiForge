from __future__ import annotations

import pytest

from app.platform.config import Settings
from app.ai.model_gateway import (
    NonRetryableModelGatewayError,
    OpenAICompatibleModelGateway,
    RetryableModelGatewayError,
    build_model_gateway,
)


def test_model_gateway_uses_openai_compatible_payload_and_masks_secret_from_response() -> None:
    calls: list[dict] = []

    def fake_transport(url: str, headers: dict[str, str], payload: dict, timeout_seconds: float) -> dict:
        calls.append({"url": url, "headers": headers, "payload": payload, "timeout": timeout_seconds})
        return {
            "id": "chatcmpl-test",
            "model": payload["model"],
            "choices": [{"message": {"content": "pong"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1},
        }

    gateway = OpenAICompatibleModelGateway(
        provider="openai-compatible",
        api_base_url="https://models.example/v1",
        api_key="sk-secret",
        default_model="test-chat-model",
        default_reasoning_effort="high",
        transport=fake_transport,
    )

    response = gateway.chat([{"role": "user", "content": "ping"}], max_tokens=8)

    assert response.provider == "openai-compatible"
    assert response.model == "test-chat-model"
    assert response.content == "pong"
    assert response.usage == {"prompt_tokens": 3, "completion_tokens": 1}
    assert response.attempts == 1
    assert calls[0]["url"] == "https://models.example/v1/chat/completions"
    assert calls[0]["headers"]["Authorization"] == "Bearer sk-secret"
    assert calls[0]["payload"]["reasoning_effort"] == "high"
    assert "sk-secret" not in repr(response)


def test_model_gateway_retries_transient_failures_three_attempts() -> None:
    attempts = 0

    def flaky_transport(_url: str, _headers: dict[str, str], _payload: dict, _timeout_seconds: float) -> dict:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RetryableModelGatewayError("rate limited")
        return {"model": "test-chat-model", "choices": [{"message": {"content": "ok"}}]}

    gateway = OpenAICompatibleModelGateway(
        provider="openai-compatible",
        api_base_url="https://models.example/v1",
        api_key="sk-secret",
        default_model="test-chat-model",
        max_attempts=3,
        transport=flaky_transport,
    )

    response = gateway.chat([{"role": "user", "content": "ping"}])

    assert response.content == "ok"
    assert response.attempts == 3
    assert attempts == 3


def test_model_gateway_clamps_retry_attempts_to_three() -> None:
    gateway = OpenAICompatibleModelGateway(
        provider="openai-compatible",
        api_base_url="https://models.example/v1",
        api_key="sk-secret",
        default_model="test-chat-model",
        max_attempts=10,
    )

    assert gateway.max_attempts == 3


def test_model_gateway_fails_fast_without_api_key() -> None:
    gateway = OpenAICompatibleModelGateway(
        provider="openai-compatible",
        api_base_url="https://models.example/v1",
        api_key="",
        default_model="test-chat-model",
    )

    with pytest.raises(NonRetryableModelGatewayError, match="API key"):
        gateway.chat([{"role": "user", "content": "ping"}])


def test_model_gateway_fails_fast_without_api_base_url() -> None:
    gateway = OpenAICompatibleModelGateway(
        provider="openai-compatible",
        api_base_url="",
        api_key="sk-secret",
        default_model="test-chat-model",
    )

    with pytest.raises(NonRetryableModelGatewayError, match="base URL"):
        gateway.chat([{"role": "user", "content": "ping"}])


def test_model_gateway_fails_fast_without_model() -> None:
    gateway = OpenAICompatibleModelGateway(
        provider="openai-compatible",
        api_base_url="https://models.example/v1",
        api_key="sk-secret",
        default_model="",
    )

    with pytest.raises(NonRetryableModelGatewayError, match="model"):
        gateway.chat([{"role": "user", "content": "ping"}])


def test_model_gateway_streams_openai_compatible_chunks() -> None:
    calls: list[dict] = []

    def fake_stream_transport(url: str, headers: dict[str, str], payload: dict, timeout_seconds: float):
        calls.append({"url": url, "headers": headers, "payload": payload, "timeout": timeout_seconds})
        yield {
            "id": "chatcmpl-stream-test",
            "model": payload["model"],
            "choices": [{"delta": {"content": "po"}}],
        }
        yield {
            "id": "chatcmpl-stream-test",
            "model": payload["model"],
            "choices": [{"delta": {"content": "ng"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1},
        }

    gateway = OpenAICompatibleModelGateway(
        provider="openai-compatible",
        api_base_url="https://models.example/v1",
        api_key="sk-secret",
        default_model="test-chat-model",
        default_reasoning_effort="high",
        stream_transport=fake_stream_transport,
    )

    chunks = list(gateway.chat_stream([{"role": "user", "content": "ping"}], max_tokens=8))

    assert "".join(chunk.content for chunk in chunks) == "pong"
    assert chunks[-1].done is True
    assert chunks[-1].usage == {"prompt_tokens": 3, "completion_tokens": 1}
    assert calls[0]["url"] == "https://models.example/v1/chat/completions"
    assert calls[0]["payload"]["stream"] is True
    assert calls[0]["payload"]["reasoning_effort"] == "high"


def test_build_model_gateway_reads_settings_without_exposing_key() -> None:
    settings = Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        model_gateway_provider="openai-compatible",
        model_gateway_api_key="sk-from-settings",
        model_gateway_api_base_url="https://gateway.example/v1",
        model_gateway_default_model="deepseek-v4-pro",
        model_gateway_reasoning_effort="high",
    )

    gateway = build_model_gateway(settings, transport=lambda *_args: {"choices": [{"message": {"content": "ok"}}]})

    assert gateway.provider == "openai-compatible"
    assert gateway.default_model == "deepseek-v4-pro"
    assert gateway.default_reasoning_effort == "high"
    assert gateway.api_base_url == "https://gateway.example/v1"


def test_model_gateway_defaults_target_deepseek_without_bundling_a_proxy() -> None:
    settings = Settings(_env_file=None, database_url="sqlite+pysqlite:///:memory:")

    gateway = build_model_gateway(settings, transport=lambda *_args: {"choices": [{"message": {"content": "ok"}}]})

    assert gateway.provider == "deepseek"
    assert gateway.api_base_url == "https://api.deepseek.com"
    assert gateway.default_model == "deepseek-v4-pro"
    assert gateway.default_reasoning_effort == "high"
