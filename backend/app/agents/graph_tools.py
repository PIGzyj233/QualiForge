from __future__ import annotations

import concurrent.futures
import json
import subprocess
import time
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents import AgentRun, AgentRunStatus, AgentToolCall, AgentToolCallStatus
from app.agents.coverage import lookup_coverage_records
from app.agents.graph_budget import BudgetTracker
from app.agents.graph_types import (
    AgentRunCancelled,
    CodeReadRangeInput,
    CodeRgFilesInput,
    CodeSearchInput,
    CoverageLookupInput,
    GitShowFileInput,
    ToolSpec,
)
from app.git.code_tools import CodeToolError
from app.git.code_tools import code_read_range as read_code_range
from app.git.code_tools import code_rg_files as list_code_files
from app.git.code_tools import code_search as search_code
from app.git.code_tools import git_show_file as show_git_file
from app.platform.telemetry import AGENT_TOOL_CALLS_TOTAL, AGENT_TOOL_DURATION_SECONDS, agent_span
from app.workspace.routes import audit, now_utc


class ToolRegistry:
    def __init__(
        self,
        *,
        db: Session,
        run: AgentRun,
        actor_email: str,
        budget: BudgetTracker,
        root: Path,
        resolved_ref: str,
        subagent_name: str,
        cancellation_checker: Callable[[str], None] | None = None,
    ):
        self.db = db
        self.run = run
        self.actor_email = actor_email
        self.budget = budget
        self.root = root
        self.resolved_ref = resolved_ref
        self.subagent_name = subagent_name
        self.cancellation_checker = cancellation_checker
        self.tools: dict[str, ToolSpec] = {}
        self._register_defaults()

    def invoke(self, name: str, payload: dict[str, Any]) -> Any:
        self._check_cancelled(f"tool:{name}:start")
        spec = self.tools[name]
        parsed = spec.input_model.model_validate(payload)
        self.budget.check_tool(spec.name, spec.budget_cost)
        started = time.monotonic()
        input_summary = spec.input_summary(parsed)[:700]
        idempotency_key = self._idempotency_key(spec.name, parsed.model_dump(mode="json"))
        try:
            result = self._run_tool_handler(spec, parsed, parallel=False)
            self._record_source_usage(spec.name, result)
        except (CodeToolError, OSError, subprocess.SubprocessError) as exc:
            self._record_tool_call(
                tool_name=spec.name,
                permission_level=spec.permission_level,
                input_summary=input_summary,
                output_summary="",
                status=AgentToolCallStatus.failed.value,
                duration_ms=int((time.monotonic() - started) * 1000),
                error_summary=str(exc)[:700],
                idempotency_key=idempotency_key,
            )
            raise

        self._check_cancelled(f"tool:{name}:complete")
        self._record_tool_call(
            tool_name=spec.name,
            permission_level=spec.permission_level,
            input_summary=input_summary,
            output_summary=spec.output_summary(result)[:1000],
            status=AgentToolCallStatus.succeeded.value,
            duration_ms=int((time.monotonic() - started) * 1000),
            error_summary="",
            idempotency_key=idempotency_key,
        )
        return result

    def invoke_parallel(self, calls: dict[str, tuple[str, dict[str, Any]]]) -> dict[str, Any]:
        prepared: dict[str, tuple[ToolSpec, BaseModel, str, str, float]] = {}
        for alias, (name, payload) in calls.items():
            self._check_cancelled(f"tool:{name}:parallel:start")
            spec = self.tools[name]
            if spec.name == "coverage_lookup":
                raise RuntimeError("coverage_lookup uses the database session and cannot run in this parallel read batch")
            parsed = spec.input_model.model_validate(payload)
            self.budget.check_tool(spec.name, spec.budget_cost)
            prepared[alias] = (
                spec,
                parsed,
                spec.input_summary(parsed)[:700],
                self._idempotency_key(spec.name, parsed.model_dump(mode="json")),
                time.monotonic(),
            )

        results: dict[str, Any] = {}
        max_workers = max(1, min(len(prepared), self.budget.max_parallel_subagents))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._run_tool_handler, spec, parsed, parallel=True): alias
                for alias, (spec, parsed, _input_summary, _idempotency_key, _started) in prepared.items()
            }
            for future in concurrent.futures.as_completed(futures):
                alias = futures[future]
                spec, _parsed, input_summary, idempotency_key, started = prepared[alias]
                try:
                    result = future.result()
                    self._record_source_usage(spec.name, result)
                except (CodeToolError, OSError, subprocess.SubprocessError) as exc:
                    self._record_tool_call(
                        tool_name=spec.name,
                        permission_level=spec.permission_level,
                        input_summary=input_summary,
                        output_summary="",
                        status=AgentToolCallStatus.failed.value,
                        duration_ms=int((time.monotonic() - started) * 1000),
                        error_summary=str(exc)[:700],
                        idempotency_key=idempotency_key,
                    )
                    raise

                self._check_cancelled(f"tool:{spec.name}:parallel:complete")
                self._record_tool_call(
                    tool_name=spec.name,
                    permission_level=spec.permission_level,
                    input_summary=input_summary,
                    output_summary=spec.output_summary(result)[:1000],
                    status=AgentToolCallStatus.succeeded.value,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    error_summary="",
                    idempotency_key=idempotency_key,
                )
                results[alias] = result
        return results

    def _run_tool_handler(self, spec: ToolSpec, parsed: BaseModel, *, parallel: bool) -> Any:
        with agent_span(
            "agent.tool_call",
            run_id=self.run.id,
            subagent=self.subagent_name,
            tool=spec.name,
            permission_level=spec.permission_level,
            parallel=parallel,
        ) as span:
            try:
                result = spec.handler(parsed)
            except Exception:
                span.set_attribute("tool_status", AgentToolCallStatus.failed.value)
                raise
            span.set_attribute("tool_status", AgentToolCallStatus.succeeded.value)
            return result

    def _check_cancelled(self, phase: str) -> None:
        if self.cancellation_checker is not None:
            self.cancellation_checker(phase)
        self.db.expire(self.run)
        if self.run.status == AgentRunStatus.cancelled.value:
            raise AgentRunCancelled("Agent run was cancelled")

    def _record_source_usage(self, tool_name: str, result: Any) -> None:
        if tool_name not in {"code_read_range", "git_show_file"}:
            return
        content = ""
        if isinstance(result, dict):
            content = str(result.get("content") or "")
        self.budget.add_source_chars(len(content))

    def _register_defaults(self) -> None:
        self._register(
            ToolSpec(
                name="code_rg_files",
                permission_level="read",
                input_model=CodeRgFilesInput,
                budget_cost=1,
                audit_policy="record_summary",
                handler=lambda item: list_code_files(self.root, path=item.path, glob=item.glob, max_results=item.max_results),
                input_summary=lambda item: f"path={item.path}; glob={item.glob or '*'}",
                output_summary=lambda files: f"Listed {len(files)} file(s)",
            )
        )
        self._register(
            ToolSpec(
                name="code_search",
                permission_level="read",
                input_model=CodeSearchInput,
                budget_cost=1,
                audit_policy="record_summary",
                handler=lambda item: [
                    match.__dict__
                    for match in search_code(self.root, pattern=item.pattern, path=item.path, max_results=item.max_results)
                ],
                input_summary=lambda item: f"path={item.path}; pattern={item.pattern[:160]}",
                output_summary=lambda items: f"Found {len(items)} match(es)",
            )
        )
        self._register(
            ToolSpec(
                name="code_read_range",
                permission_level="read",
                input_model=CodeReadRangeInput,
                budget_cost=1,
                audit_policy="record_summary",
                handler=lambda item: read_code_range(
                    self.root,
                    path=item.path,
                    start_line=item.start_line,
                    end_line=item.end_line,
                    numbered=True,
                ).__dict__,
                input_summary=lambda item: f"{item.path}:{item.start_line}-{item.end_line}",
                output_summary=lambda item: f"Read {item['path']}:{item['start_line']}-{item['end_line']}",
            )
        )
        self._register(
            ToolSpec(
                name="git_show_file",
                permission_level="read",
                input_model=GitShowFileInput,
                budget_cost=1,
                audit_policy="record_summary",
                handler=lambda item: show_git_file(self.root, ref=self.resolved_ref, path=item.path).__dict__,
                input_summary=lambda item: f"{self.resolved_ref}:{item.path}",
                output_summary=lambda item: f"Read {item['path']} at resolved ref",
            )
        )
        self._register(
            ToolSpec(
                name="coverage_lookup",
                permission_level="read",
                input_model=CoverageLookupInput,
                budget_cost=1,
                audit_policy="record_summary",
                handler=lambda item: lookup_coverage_records(
                    self.db,
                    run=self.run,
                    query=item.query,
                    module_key=item.module_key,
                    max_results=item.max_results,
                ),
                input_summary=lambda item: f"module_key={item.module_key or '*'}; query={item.query[:160]}",
                output_summary=lambda items: f"Found {len(items)} coverage/candidate record(s)",
            )
        )

    def _register(self, spec: ToolSpec) -> None:
        self.tools[spec.name] = spec

    def _record_tool_call(
        self,
        *,
        tool_name: str,
        permission_level: str,
        input_summary: str,
        output_summary: str,
        status: str,
        duration_ms: int,
        error_summary: str,
        idempotency_key: str,
    ) -> None:
        tool_call = AgentToolCall(
            agent_run_id=self.run.id,
            subagent_name=self.subagent_name,
            tool_name=tool_name,
            permission_level=permission_level,
            input_summary=input_summary,
            output_summary=output_summary,
            status=status,
            idempotency_key=idempotency_key,
            duration_ms=duration_ms,
            error_summary=error_summary,
            completed_at=now_utc(),
        )
        self.db.add(tool_call)
        self.db.flush()
        AGENT_TOOL_CALLS_TOTAL.labels(tool=tool_name, status=status).inc()
        AGENT_TOOL_DURATION_SECONDS.labels(tool=tool_name, status=status).observe(max(0, duration_ms) / 1000)
        audit(
            self.db,
            workspace_id=self.run.workspace_id,
            actor_email=self.actor_email,
            action="agent_tool_call.recorded",
            entity_type="AgentToolCall",
            entity_id=tool_call.id,
            summary=f"Recorded {permission_level} tool call {tool_name}",
            after={
                "agent_run_id": self.run.id,
                "tool_name": tool_name,
                "permission_level": permission_level,
                "status": status,
                "subagent_name": self.subagent_name,
                "idempotency_key": idempotency_key,
            },
        )
        self.db.commit()

    def _idempotency_key(self, tool_name: str, payload: dict[str, Any]) -> str:
        digest = sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:24]
        return f"{self.run.id}:{tool_name}:{digest}"


