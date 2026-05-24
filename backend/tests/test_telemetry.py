from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.telemetry import agent_span, export_langfuse_generation, parse_otlp_headers


class FakeSpan:
    def __init__(self, name: str):
        self.name = name
        self.attributes = {}
        self.exceptions = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def set_attribute(self, key, value):
        self.attributes[key] = value

    def record_exception(self, exc):
        self.exceptions.append(exc)


class FakeTracer:
    def __init__(self):
        self.spans = []

    def start_as_current_span(self, name: str):
        span = FakeSpan(name)
        self.spans.append(span)
        return span


def test_parse_otlp_headers_ignores_blank_or_invalid_items() -> None:
    assert parse_otlp_headers("Authorization=Bearer token, x-tenant = qa , broken") == {
        "Authorization": "Bearer token",
        "x-tenant": "qa",
    }


def test_agent_span_records_attributes_and_exceptions(monkeypatch) -> None:
    fake_tracer = FakeTracer()
    monkeypatch.setattr("app.telemetry.tracer", fake_tracer)

    with agent_span("agent.test", run_id="run-1", retry=False) as span:
        span.set_attribute("custom", "value")

    assert fake_tracer.spans[0].name == "agent.test"
    assert fake_tracer.spans[0].attributes["run_id"] == "run-1"
    assert fake_tracer.spans[0].attributes["retry"] is False
    assert fake_tracer.spans[0].attributes["custom"] == "value"

    with pytest.raises(ValueError):
        with agent_span("agent.failure", phase="tool"):
            raise ValueError("span boom")

    failure_span = fake_tracer.spans[1]
    assert failure_span.attributes["phase"] == "tool"
    assert failure_span.attributes["error.type"] == "ValueError"
    assert failure_span.exceptions[0].args == ("span boom",)


def test_api_request_span_records_http_metadata(monkeypatch) -> None:
    fake_tracer = FakeTracer()
    settings = Settings(database_url="sqlite+pysqlite:///:memory:", redis_url="redis://localhost:6379/15")
    client = TestClient(create_app(settings))
    monkeypatch.setattr("app.telemetry.tracer", fake_tracer)

    response = client.get("/api/health")

    assert response.status_code == 200
    request_span = next(span for span in fake_tracer.spans if span.name == "api.request")
    assert request_span.attributes["http_method"] == "GET"
    assert request_span.attributes["http_path"] == "/api/health"
    assert request_span.attributes["http_status_code"] == 200


def test_langfuse_generation_export_uses_prompt_metadata_without_raw_prompt(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr("app.telemetry.urllib.request.urlopen", fake_urlopen)
    settings = Settings(
        _env_file=None,
        telemetry_langfuse_enabled=True,
        telemetry_langfuse_host="https://langfuse.local",
        telemetry_langfuse_public_key="pk-lf-test",
        telemetry_langfuse_secret_key="sk-lf-test",
    )
    invocation = SimpleNamespace(
        id="invocation-1",
        workspace_id="workspace-1",
        agent_run_id="run-1",
        actor_email="owner@qualiforge.local",
        purpose="case_generation",
        subagent_name="CaseDesignSubAgent",
        model_name="qf-supervisor-strong",
        model_alias="qf-supervisor-strong",
        input_summary="LangGraph supervisor case generation for agent run run-1",
        input_data_types=["goal", "source_code_excerpt"],
        prompt_hash="hash-only-no-prompt",
        prompt_version="agent-supervisor-v1",
        status="succeeded",
        provider_name="litellm",
        attempts=1,
        latency_ms=12,
        includes_source_code=True,
        failure_reason="",
        usage={"prompt_tokens": 10, "completion_tokens": 5},
    )

    export_langfuse_generation(settings, invocation)

    assert captured["url"] == "https://langfuse.local/api/public/ingestion"
    expected_auth = "Basic " + base64.b64encode(b"pk-lf-test:sk-lf-test").decode("ascii")
    assert captured["headers"]["Authorization"] == expected_auth
    generation = captured["body"]["batch"][1]["body"]
    assert generation["input"]["prompt_hash"] == "hash-only-no-prompt"
    assert generation["input"]["prompt_version"] == "agent-supervisor-v1"
    serialized = json.dumps(captured["body"])
    assert "raw prompt" not in serialized.lower()
    assert "sk-lf-test" not in serialized
