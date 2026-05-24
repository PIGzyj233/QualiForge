from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.model_gateway import (
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
        provider="deepseek",
        api_base_url="https://api.deepseek.example/v1",
        api_key="sk-secret",
        default_model="deepseek-v4-flash",
        transport=fake_transport,
    )

    response = gateway.chat([{"role": "user", "content": "ping"}], max_tokens=8)

    assert response.provider == "deepseek"
    assert response.model == "deepseek-v4-flash"
    assert response.content == "pong"
    assert response.usage == {"prompt_tokens": 3, "completion_tokens": 1}
    assert response.attempts == 1
    assert calls[0]["url"] == "https://api.deepseek.example/v1/chat/completions"
    assert calls[0]["headers"]["Authorization"] == "Bearer sk-secret"
    assert "sk-secret" not in repr(response)


def test_model_gateway_retries_transient_failures_three_attempts() -> None:
    attempts = 0

    def flaky_transport(_url: str, _headers: dict[str, str], _payload: dict, _timeout_seconds: float) -> dict:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RetryableModelGatewayError("rate limited")
        return {"model": "deepseek-v4-flash", "choices": [{"message": {"content": "ok"}}]}

    gateway = OpenAICompatibleModelGateway(
        provider="deepseek",
        api_base_url="https://api.deepseek.example/v1",
        api_key="sk-secret",
        default_model="deepseek-v4-flash",
        max_attempts=3,
        transport=flaky_transport,
    )

    response = gateway.chat([{"role": "user", "content": "ping"}])

    assert response.content == "ok"
    assert response.attempts == 3
    assert attempts == 3


def test_model_gateway_clamps_retry_attempts_to_three() -> None:
    gateway = OpenAICompatibleModelGateway(
        provider="deepseek",
        api_base_url="https://api.deepseek.example/v1",
        api_key="sk-secret",
        default_model="deepseek-v4-flash",
        max_attempts=10,
    )

    assert gateway.max_attempts == 3


def test_model_gateway_fails_fast_without_api_key() -> None:
    gateway = OpenAICompatibleModelGateway(
        provider="deepseek",
        api_base_url="https://api.deepseek.example/v1",
        api_key="",
        default_model="deepseek-v4-flash",
    )

    with pytest.raises(NonRetryableModelGatewayError, match="API key"):
        gateway.chat([{"role": "user", "content": "ping"}])


def test_build_model_gateway_reads_settings_without_exposing_key() -> None:
    settings = Settings(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        model_gateway_provider="deepseek",
        model_gateway_api_key="sk-from-settings",
        model_gateway_api_base_url="https://gateway.example/v1",
        model_gateway_default_model="deepseek-v4-flash",
    )

    gateway = build_model_gateway(settings, transport=lambda *_args: {"choices": [{"message": {"content": "ok"}}]})

    assert gateway.provider == "deepseek"
    assert gateway.default_model == "deepseek-v4-flash"
    assert gateway.api_base_url == "https://gateway.example/v1"


def test_litellm_proxy_config() -> None:
    settings = Settings(_env_file=None, database_url="sqlite+pysqlite:///:memory:")

    gateway = build_model_gateway(settings, transport=lambda *_args: {"choices": [{"message": {"content": "ok"}}]})

    assert gateway.provider == "litellm"
    assert gateway.api_base_url == "http://litellm:4000/v1"
    assert gateway.default_model == "qf-supervisor-strong"


def test_litellm_proxy_compose_and_alias_config_do_not_expose_provider_secret() -> None:
    compose = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text(encoding="utf-8")
    litellm_config = (Path(__file__).resolve().parents[2] / "litellm.config.yaml").read_text(encoding="utf-8")

    assert "litellm:" in compose
    assert "http://litellm:4000/v1" in compose
    assert "qf-supervisor-strong" in litellm_config
    assert "deepseek/deepseek-v4-flash" in litellm_config
    assert "api-key-here" not in compose
    assert "api-key-here" not in litellm_config
