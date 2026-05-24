from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.agents.activities import (
        execute_agent_child_task_activity,
        execute_agent_graph_activity,
        mark_agent_run_cancelled_activity,
        mark_agent_run_failed_activity,
    )


def _activity_timeout(payload: dict[str, Any], key: str, default_seconds: int) -> timedelta:
    try:
        seconds = max(1, int(payload.get(key) or default_seconds))
    except (TypeError, ValueError):
        seconds = default_seconds
    return timedelta(seconds=seconds)


@workflow.defn
class AgentChildTaskWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        task_kind = str(payload.get("task_kind") or payload.get("kind") or "agent_child_task")
        try:
            result = await workflow.execute_activity(
                execute_agent_child_task_activity,
                payload,
                start_to_close_timeout=_activity_timeout(payload, "child_activity_start_to_close_timeout_seconds", 2 * 60),
                heartbeat_timeout=_activity_timeout(payload, "child_activity_heartbeat_timeout_seconds", 30),
                retry_policy=RetryPolicy(maximum_attempts=max(1, int(payload.get("child_activity_retry_attempts") or 2))),
            )
        except Exception as exc:
            result = {
                "status": "failed",
                "task_kind": task_kind,
                "parent_run_id": str(payload.get("parent_run_id") or payload.get("run_id") or ""),
                "summary": f"Child task {task_kind} failed: {exc.__class__.__name__}: {str(exc)[:300]}",
            }
        result_payload = dict(result) if isinstance(result, dict) else {}
        return {
            **result_payload,
            "status": str(result_payload.get("status") or "succeeded"),
            "task_kind": task_kind,
            "parent_run_id": str(payload.get("parent_run_id") or payload.get("run_id") or ""),
            "workflow_id": workflow.info().workflow_id,
            "summary": str(result_payload.get("summary") or payload.get("summary") or f"Completed child task {task_kind}"),
        }


@workflow.defn
class AgentRunWorkflow:
    def __init__(self) -> None:
        self._resume_payload: dict[str, Any] | None = None
        self._cancel_reason = ""

    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        current_payload = dict(payload)
        try:
            child_results = await self._execute_child_tasks(payload)
            if child_results:
                current_payload["child_results"] = child_results
            while True:
                result = await workflow.execute_activity(
                    execute_agent_graph_activity,
                    current_payload,
                    start_to_close_timeout=_activity_timeout(payload, "activity_start_to_close_timeout_seconds", 25 * 60),
                    heartbeat_timeout=_activity_timeout(payload, "activity_heartbeat_timeout_seconds", 30),
                    retry_policy=RetryPolicy(maximum_attempts=max(1, int(payload.get("activity_retry_attempts") or 3))),
                )
                if result.get("status") != "waiting_for_user":
                    return result

                await workflow.wait_condition(lambda: self._resume_payload is not None or bool(self._cancel_reason))
                if self._cancel_reason:
                    return await workflow.execute_activity(
                        mark_agent_run_cancelled_activity,
                        {
                            "workspace_id": payload["workspace_id"],
                            "run_id": payload["run_id"],
                            "actor_email": payload["actor_email"],
                            "cancel_reason": self._cancel_reason,
                        },
                        start_to_close_timeout=timedelta(seconds=15),
                    )

                resume_payload = self._resume_payload or {}
                self._resume_payload = None
                current_payload = {
                    **payload,
                    "explicit_resume": True,
                    "budget_snapshot": dict(resume_payload.get("budget_snapshot") or {}),
                    "resume_reason": str(resume_payload.get("resume_reason") or ""),
                }
                if child_results:
                    current_payload["child_results"] = child_results
        except asyncio.CancelledError:
            await asyncio.shield(
                workflow.execute_activity(
                    mark_agent_run_cancelled_activity,
                    {
                        "workspace_id": payload["workspace_id"],
                        "run_id": payload["run_id"],
                        "actor_email": payload["actor_email"],
                        "cancel_reason": self._cancel_reason or "Temporal workflow cancelled",
                    },
                    start_to_close_timeout=timedelta(seconds=15),
                )
            )
            raise
        except Exception as exc:
            return await workflow.execute_activity(
                mark_agent_run_failed_activity,
                {
                    "workspace_id": payload["workspace_id"],
                    "run_id": payload["run_id"],
                    "actor_email": payload["actor_email"],
                    "failure_reason": f"Temporal activity failed after retries: {exc.__class__.__name__}: {str(exc)[:500]}",
                    "phase": "temporal_failed",
                },
                start_to_close_timeout=timedelta(seconds=15),
            )

    @workflow.signal
    async def resume_with_budget(self, payload: dict[str, Any]) -> None:
        self._resume_payload = dict(payload)

    @workflow.signal
    async def cancel_with_reason(self, payload: dict[str, Any]) -> None:
        self._cancel_reason = str(payload.get("cancel_reason") or "Agent run cancelled by user")

    async def _execute_child_tasks(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        raw_tasks = payload.get("child_tasks") or []
        if not isinstance(raw_tasks, list):
            return []
        results: list[dict[str, Any]] = []
        for index, raw_task in enumerate(raw_tasks):
            if not isinstance(raw_task, dict):
                continue
            task_kind = str(raw_task.get("task_kind") or raw_task.get("kind") or f"child_{index}")
            child_payload = {
                **raw_task,
                "task_kind": task_kind,
                "parent_run_id": payload["run_id"],
                "workspace_id": payload["workspace_id"],
                "project_id": payload.get("project_id") or "",
                "repository_id": payload.get("repository_id") or "",
                "ref": payload.get("ref") or "",
                "actor_email": payload.get("actor_email") or "",
            }
            result = await workflow.execute_child_workflow(
                AgentChildTaskWorkflow.run,
                child_payload,
                id=f"agent-run-{payload['run_id']}-child-{index}-{task_kind}",
                task_queue=payload.get("task_queue") or None,
                execution_timeout=_activity_timeout(payload, "child_workflow_timeout_seconds", 10 * 60),
            )
            results.append(result)
        return results
