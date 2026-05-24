from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app.agent_activities import (
    execute_agent_child_task_activity_with_settings,
    execute_agent_graph_activity_with_settings,
    mark_agent_run_cancelled_with_settings,
    mark_agent_run_failed_with_settings,
)
from app.agent_workflows import AgentChildTaskWorkflow, AgentRunWorkflow
from test_agents import (
    OWNER,
    bind_repository,
    create_agent_run,
    create_refund_fixture_repo,
    create_workspace_project,
    make_client,
    sync_repository,
)


async def _request_json(call: Callable[[], Any]) -> Any:
    response = await asyncio.to_thread(call)
    try:
        body = response.json()
    except Exception:
        body = response.text
    assert response.status_code < 400, body
    return body


async def _wait_for_detail(client, workspace_id: str, run_id: str, predicate, *, label: str) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + 20
    last_detail: dict[str, Any] | None = None
    detail_url = f"/api/workspaces/{workspace_id}/agent/runs/{run_id}/execution-detail"
    while asyncio.get_running_loop().time() < deadline:
        response = await asyncio.to_thread(client.get, detail_url)
        assert response.status_code == 200, response.json()
        last_detail = response.json()
        if predicate(last_detail):
            return last_detail
        await asyncio.sleep(0.1)
    raise AssertionError(f"Timed out waiting for {label}; last detail: {last_detail}")


def test_temporal_api_execute_resume_cancel_roundtrip_with_real_worker(tmp_path: Path) -> None:
    async def scenario() -> None:
        env = await WorkflowEnvironment.start_time_skipping()
        task_queue = f"agent-api-{uuid4().hex}"
        settings_overrides = {
            "database_url": f"sqlite+pysqlite:///{tmp_path / 'temporal-api.db'}",
            "agent_execute_sync_mode": False,
            "temporal_address": env.client.service_client.config.target_host,
            "temporal_namespace": env.client.namespace,
            "agent_task_queue": task_queue,
            "agent_activity_start_to_close_timeout_minutes": 1,
            "agent_activity_heartbeat_timeout_seconds": 5,
            "agent_activity_retry_attempts": 1,
        }
        client = make_client(tmp_path, settings_overrides=settings_overrides)
        settings = client.app.state.settings

        @activity.defn(name="execute_agent_child_task_activity")
        async def execute_child_activity(payload: dict[str, Any]) -> dict[str, Any]:
            return execute_agent_child_task_activity_with_settings(payload, settings=settings)

        @activity.defn(name="execute_agent_graph_activity")
        async def execute_graph_activity(payload: dict[str, Any]) -> dict[str, Any]:
            return execute_agent_graph_activity_with_settings(payload, settings=settings)

        @activity.defn(name="mark_agent_run_cancelled_activity")
        async def mark_cancelled_activity(payload: dict[str, Any]) -> dict[str, Any]:
            return mark_agent_run_cancelled_with_settings(payload, settings=settings)

        @activity.defn(name="mark_agent_run_failed_activity")
        async def mark_failed_activity(payload: dict[str, Any]) -> dict[str, Any]:
            return mark_agent_run_failed_with_settings(payload, settings=settings)

        try:
            workspace, project = create_workspace_project(client)
            source = create_refund_fixture_repo(tmp_path)
            repository = bind_repository(client, workspace["id"], project["id"], source)
            repository = sync_repository(client, workspace["id"], project["id"], repository["id"])
            run = create_agent_run(
                client,
                workspace["id"],
                project["id"],
                budget_snapshot={
                    "max_tool_calls": 40,
                    "max_model_calls": 0,
                    "max_subagents": 4,
                    "max_parallel_subagents": 3,
                    "max_wall_time_minutes": 5,
                    "max_total_source_chars_sent": 20000,
                    "child_tasks": [{"task_kind": "large_repo_scan", "summary": "Scan synced repository before graph"}],
                },
            )

            async with Worker(
                env.client,
                task_queue=task_queue,
                workflows=[AgentRunWorkflow, AgentChildTaskWorkflow],
                activities=[execute_child_activity, execute_graph_activity, mark_cancelled_activity, mark_failed_activity],
            ):
                execute_payload = await _request_json(
                    lambda: client.post(
                        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execute?actor_email={OWNER}",
                        json={"repository_id": repository["id"], "ref": "master", "candidate_limit": 3},
                    )
                )
                assert execute_payload["run"]["temporal_workflow_id"] == f"agent-run-{run['id']}"
                assert execute_payload["staged_outputs"] == []

                waiting_detail = await _wait_for_detail(
                    client,
                    workspace["id"],
                    run["id"],
                    lambda detail: detail["run"]["status"] == "waiting_for_user"
                    and "model budget exceeded" in detail["run"]["failure_reason"],
                    label="Temporal agent budget waiting state",
                )
                child_results = waiting_detail["budget"]["snapshot"]["temporal_child_results"]
                assert child_results[0]["task_kind"] == "large_repo_scan"
                assert child_results[0]["status"] == "succeeded"
                assert child_results[0]["workflow_id"].startswith(f"agent-run-{run['id']}-child-0-large_repo_scan")

                resume_payload = await _request_json(
                    lambda: client.post(
                        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/resume?actor_email={OWNER}",
                        json={
                            "budget_snapshot": {"max_model_calls": 0},
                            "resume_reason": "Verify real Temporal resume signal keeps waiting for budget",
                        },
                    )
                )
                assert resume_payload["summary"] == "Agent workflow resume signal sent"

                await _wait_for_detail(
                    client,
                    workspace["id"],
                    run["id"],
                    lambda detail: detail["run"]["current_phase"] == "budget_waiting"
                    and "model budget exceeded" in detail["run"]["failure_reason"],
                    label="Temporal resumed activity budget waiting state",
                )

                cancelled = await _request_json(
                    lambda: client.post(
                        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/cancel?actor_email={OWNER}",
                        json={"cancel_reason": "Stop real Temporal integration run"},
                    )
                )
                assert cancelled["status"] == "cancelled"

                cancelled_detail = await _wait_for_detail(
                    client,
                    workspace["id"],
                    run["id"],
                    lambda detail: detail["run"]["status"] == "cancelled",
                    label="Temporal agent cancellation",
                )
                assert cancelled_detail["run"]["failure_reason"] == "Stop real Temporal integration run"
        finally:
            await env.shutdown()

    asyncio.run(scenario())


def test_execute_activity_returns_cancelled_when_run_was_already_cancelled(tmp_path: Path) -> None:
    client = make_client(
        tmp_path,
        settings_overrides={
            "database_url": f"sqlite+pysqlite:///{tmp_path / 'temporal-cancelled-activity.db'}",
            "agent_execute_sync_mode": False,
        },
    )
    settings = client.app.state.settings
    workspace, project = create_workspace_project(client)
    run = create_agent_run(client, workspace["id"], project["id"])

    cancel_response = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/cancel?actor_email={OWNER}",
        json={"cancel_reason": "Already cancelled before resumed Temporal activity"},
    )
    assert cancel_response.status_code == 200, cancel_response.json()

    result = execute_agent_graph_activity_with_settings(
        {
            "workspace_id": workspace["id"],
            "run_id": run["id"],
            "repository_id": "repo-not-needed-after-cancel",
            "ref": "master",
            "candidate_limit": 3,
            "actor_email": OWNER,
            "explicit_resume": True,
        },
        settings=settings,
    )

    assert result["status"] == "cancelled"
    assert result["summary"] == "Already cancelled before resumed Temporal activity"
