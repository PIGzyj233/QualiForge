from __future__ import annotations

import base64
import json
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Iterator
import urllib.error
import urllib.request

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SimpleSpanProcessor
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest


tracer = trace.get_tracer("qualiforge.agent")
_configured = False

AGENT_RUNS_TOTAL = Counter("qualiforge_agent_runs_total", "Agent runs by terminal status.", ["status"])
AGENT_RUN_QUEUE_TIME_SECONDS = Histogram("qualiforge_agent_run_queue_time_seconds", "Agent run queue time before execution starts.")
AGENT_RUN_DURATION_SECONDS = Histogram("qualiforge_agent_run_duration_seconds", "Agent run duration in seconds.")
AGENT_TOOL_CALLS_TOTAL = Counter("qualiforge_agent_tool_calls_total", "Agent tool calls by tool and status.", ["tool", "status"])
AGENT_TOOL_DURATION_SECONDS = Histogram(
    "qualiforge_agent_tool_duration_seconds", "Agent tool duration in seconds by tool and status.", ["tool", "status"]
)
AGENT_MODEL_CALLS_TOTAL = Counter("qualiforge_agent_model_calls_total", "Agent model calls by model and status.", ["model", "status"])
AGENT_MODEL_TOKENS_TOTAL = Counter(
    "qualiforge_agent_model_tokens_total", "Agent model tokens by model and token type.", ["model", "token_type"]
)
AGENT_MODEL_COST_TOTAL = Counter("qualiforge_agent_model_cost_total", "Agent estimated model cost by model.", ["model"])
AGENT_MODEL_LATENCY_SECONDS = Histogram(
    "qualiforge_agent_model_latency_seconds", "Agent model latency in seconds by model and status.", ["model", "status"]
)
AGENT_STAGED_OUTPUT_DECISIONS_TOTAL = Counter(
    "qualiforge_agent_staged_output_decisions_total",
    "Agent staged output decisions by output type and status.",
    ["output_type", "status"],
)
AGENT_APPROVAL_WAIT_SECONDS = Histogram(
    "qualiforge_agent_approval_wait_seconds", "Agent approval wait time in seconds by approval type and status.", ["approval_type", "status"]
)


def parse_otlp_headers(raw_headers: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for item in raw_headers.split(","):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        if key:
            headers[key] = value.strip()
    return headers


def configure_telemetry(settings) -> None:
    global _configured, tracer
    if _configured:
        return
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": settings.telemetry_service_name,
                "deployment.environment": settings.environment,
            }
        )
    )
    if settings.telemetry_otlp_enabled:
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=settings.telemetry_otlp_endpoint or None,
                    headers=parse_otlp_headers(settings.telemetry_otlp_headers),
                    timeout=5,
                )
            )
        )
    if settings.telemetry_trace_console_enabled:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer("qualiforge.agent")
    _configured = True


@contextmanager
def agent_span(name: str, **attributes: object) -> Iterator[Any]:
    with tracer.start_as_current_span(name) as span:
        for key, value in attributes.items():
            span.set_attribute(key, value if isinstance(value, (str, bool, int, float)) else str(value))
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_attribute("error.type", exc.__class__.__name__)
            span.set_attribute("error.message", str(exc)[:700])
            raise


def prometheus_response() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST


def elapsed_seconds(start: datetime, end: datetime) -> float:
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    return max(0, (end - start).total_seconds())


def export_langfuse_generation(settings, invocation) -> None:
    if not settings.telemetry_langfuse_enabled:
        return
    if not settings.telemetry_langfuse_host or not settings.telemetry_langfuse_public_key or not settings.telemetry_langfuse_secret_key:
        return
    host = settings.telemetry_langfuse_host.rstrip("/")
    url = f"{host}/api/public/ingestion"
    trace_id = invocation.agent_run_id or invocation.id
    now = datetime.now(UTC).isoformat()
    body = {
        "batch": [
            {
                "id": f"trace-{trace_id}",
                "type": "trace-create",
                "timestamp": now,
                "body": {
                    "id": trace_id,
                    "name": "qualiforge.agent_run",
                    "userId": invocation.actor_email,
                    "metadata": {
                        "workspace_id": invocation.workspace_id,
                        "agent_run_id": invocation.agent_run_id,
                        "purpose": invocation.purpose,
                    },
                },
            },
            {
                "id": f"generation-{invocation.id}",
                "type": "generation-create",
                "timestamp": now,
                "body": {
                    "id": invocation.id,
                    "traceId": trace_id,
                    "name": invocation.subagent_name or "AgentModelCall",
                    "model": invocation.model_name or invocation.model_alias,
                    "input": {
                        "summary": invocation.input_summary,
                        "data_types": invocation.input_data_types,
                        "prompt_hash": invocation.prompt_hash,
                        "prompt_version": invocation.prompt_version,
                    },
                    "metadata": {
                        "status": invocation.status,
                        "provider": invocation.provider_name,
                        "model_alias": invocation.model_alias,
                        "subagent_name": invocation.subagent_name,
                        "attempts": invocation.attempts,
                        "latency_ms": invocation.latency_ms,
                        "includes_source_code": invocation.includes_source_code,
                        "failure_reason": invocation.failure_reason,
                    },
                    "usage": invocation.usage or {},
                },
            },
        ]
    }
    credentials = f"{settings.telemetry_langfuse_public_key}:{settings.telemetry_langfuse_secret_key}".encode("utf-8")
    headers = {
        "Authorization": f"Basic {base64.b64encode(credentials).decode('ascii')}",
        "Content-Type": "application/json",
    }
    request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=2) as response:  # noqa: S310 - configured Langfuse endpoint.
            response.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return
