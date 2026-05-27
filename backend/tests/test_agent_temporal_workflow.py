from __future__ import annotations

import asyncio
from uuid import uuid4

from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app.agents.workflows import AgentChildTaskWorkflow, AgentRunWorkflow


def run_async(coro):
    return asyncio.run(coro)


def workflow_payload(task_queue: str, run_id: str | None = None) -> dict:
    return {
        "workspace_id": "workspace-temporal-test",
        "run_id": run_id or uuid4().hex,
        "project_id": "project-temporal-test",
        "repository_id": "repo-temporal-test",
        "ref": "main",
        "candidate_limit": 3,
        "actor_email": "owner@qualiforge.local",
        "activity_start_to_close_timeout_seconds": 5,
        "activity_heartbeat_timeout_seconds": 5,
        "activity_retry_attempts": 3,
        "task_queue": task_queue,
    }


def test_agent_run_workflow_retries_activity_to_success() -> None:
    attempts: list[dict] = []

    @activity.defn(name="execute_agent_graph_activity")
    async def execute_agent_graph_activity(payload: dict) -> dict:
        attempts.append(dict(payload))
        if len(attempts) < 3:
            raise RuntimeError("transient graph failure")
        return {"run_id": payload["run_id"], "status": "succeeded", "summary": "ok", "staged_output_count": 1}

    @activity.defn(name="mark_agent_run_cancelled_activity")
    async def mark_agent_run_cancelled_activity(payload: dict) -> dict:
        return {"run_id": payload["run_id"], "status": "cancelled", "summary": payload["cancel_reason"]}

    @activity.defn(name="mark_agent_run_failed_activity")
    async def mark_agent_run_failed_activity(payload: dict) -> dict:
        return {"run_id": payload["run_id"], "status": "failed", "summary": payload["failure_reason"]}

    async def scenario() -> None:
        env = await WorkflowEnvironment.start_time_skipping()
        task_queue = f"agent-test-{uuid4().hex}"
        async with Worker(
            env.client,
            task_queue=task_queue,
            workflows=[AgentRunWorkflow],
            activities=[execute_agent_graph_activity, mark_agent_run_cancelled_activity, mark_agent_run_failed_activity],
        ):
            result = await env.client.execute_workflow(
                AgentRunWorkflow.run,
                workflow_payload(task_queue),
                id=f"agent-run-test-{uuid4().hex}",
                task_queue=task_queue,
            )
        await env.shutdown()
        assert result["status"] == "succeeded"

    run_async(scenario())
    assert len(attempts) == 3


def test_agent_run_workflow_runs_child_tasks_before_activity() -> None:
    activity_payloads: list[dict] = []
    child_payloads: list[dict] = []

    @activity.defn(name="execute_agent_child_task_activity")
    async def execute_agent_child_task_activity(payload: dict) -> dict:
        child_payloads.append(dict(payload))
        return {
            "status": "succeeded",
            "task_kind": payload["task_kind"],
            "parent_run_id": payload["parent_run_id"],
            "summary": f"activity completed {payload['task_kind']}",
        }

    @activity.defn(name="execute_agent_graph_activity")
    async def execute_agent_graph_activity(payload: dict) -> dict:
        activity_payloads.append(dict(payload))
        return {
            "run_id": payload["run_id"],
            "status": "succeeded",
            "summary": f"{len(payload.get('child_results') or [])} child tasks",
            "staged_output_count": 0,
        }

    @activity.defn(name="mark_agent_run_cancelled_activity")
    async def mark_agent_run_cancelled_activity(payload: dict) -> dict:
        return {"run_id": payload["run_id"], "status": "cancelled", "summary": payload["cancel_reason"]}

    @activity.defn(name="mark_agent_run_failed_activity")
    async def mark_agent_run_failed_activity(payload: dict) -> dict:
        return {"run_id": payload["run_id"], "status": "failed", "summary": payload["failure_reason"]}

    async def scenario() -> None:
        env = await WorkflowEnvironment.start_time_skipping()
        task_queue = f"agent-test-{uuid4().hex}"
        payload = workflow_payload(task_queue)
        payload["child_tasks"] = [
            {"task_kind": "large_repo_scan", "summary": "Scan repository routes"},
            {"task_kind": "large_import_analysis", "summary": "Analyze imported rows"},
        ]
        async with Worker(
            env.client,
            task_queue=task_queue,
            workflows=[AgentRunWorkflow, AgentChildTaskWorkflow],
            activities=[
                execute_agent_child_task_activity,
                execute_agent_graph_activity,
                mark_agent_run_cancelled_activity,
                mark_agent_run_failed_activity,
            ],
        ):
            result = await env.client.execute_workflow(
                AgentRunWorkflow.run,
                payload,
                id=f"agent-run-test-{uuid4().hex}",
                task_queue=task_queue,
            )
        await env.shutdown()
        assert result["status"] == "succeeded"
        assert result["summary"] == "2 child tasks"

    run_async(scenario())
    assert [item["task_kind"] for item in child_payloads] == ["large_repo_scan", "large_import_analysis"]
    assert all(item["project_id"] == "project-temporal-test" for item in child_payloads)
    assert all(item["repository_id"] == "repo-temporal-test" for item in child_payloads)
    assert all(item["ref"] == "main" for item in child_payloads)
    assert len(activity_payloads) == 1
    child_results = activity_payloads[0]["child_results"]
    assert [item["task_kind"] for item in child_results] == ["large_repo_scan", "large_import_analysis"]
    assert all(item["status"] == "succeeded" for item in child_results)
    assert all(item["parent_run_id"] == activity_payloads[0]["run_id"] for item in child_results)
    assert all(item["summary"].startswith("activity completed") for item in child_results)


def test_agent_run_workflow_resume_signal_restarts_waiting_activity_with_budget() -> None:
    activity_payloads: list[dict] = []

    @activity.defn(name="execute_agent_graph_activity")
    async def execute_agent_graph_activity(payload: dict) -> dict:
        activity_payloads.append(dict(payload))
        if not payload.get("explicit_resume"):
            return {"run_id": payload["run_id"], "status": "waiting_for_user", "summary": "budget", "staged_output_count": 0}
        return {"run_id": payload["run_id"], "status": "succeeded", "summary": "resumed", "staged_output_count": 1}

    @activity.defn(name="mark_agent_run_cancelled_activity")
    async def mark_agent_run_cancelled_activity(payload: dict) -> dict:
        return {"run_id": payload["run_id"], "status": "cancelled", "summary": payload["cancel_reason"]}

    @activity.defn(name="mark_agent_run_failed_activity")
    async def mark_agent_run_failed_activity(payload: dict) -> dict:
        return {"run_id": payload["run_id"], "status": "failed", "summary": payload["failure_reason"]}

    async def scenario() -> None:
        env = await WorkflowEnvironment.start_time_skipping()
        task_queue = f"agent-test-{uuid4().hex}"
        async with Worker(
            env.client,
            task_queue=task_queue,
            workflows=[AgentRunWorkflow],
            activities=[execute_agent_graph_activity, mark_agent_run_cancelled_activity, mark_agent_run_failed_activity],
        ):
            handle = await env.client.start_workflow(
                AgentRunWorkflow.run,
                workflow_payload(task_queue),
                id=f"agent-run-test-{uuid4().hex}",
                task_queue=task_queue,
            )
            while len(activity_payloads) < 1:
                await asyncio.sleep(0.05)
            await handle.signal(
                AgentRunWorkflow.resume_with_budget,
                {"budget_snapshot": {"max_model_calls": 5}, "resume_reason": "continue"},
            )
            result = await handle.result()
        await env.shutdown()
        assert result["status"] == "succeeded"

    run_async(scenario())
    assert len(activity_payloads) == 2
    assert activity_payloads[1]["explicit_resume"] is True
    assert activity_payloads[1]["budget_snapshot"] == {"max_model_calls": 5}
    assert activity_payloads[1]["resume_reason"] == "continue"


def test_agent_run_workflow_cancellation_calls_cancel_activity() -> None:
    execute_payloads: list[dict] = []
    cancelled_payloads: list[dict] = []

    @activity.defn(name="execute_agent_graph_activity")
    async def execute_agent_graph_activity(payload: dict) -> dict:
        execute_payloads.append(dict(payload))
        return {"run_id": payload["run_id"], "status": "waiting_for_user", "summary": "waiting", "staged_output_count": 0}

    @activity.defn(name="mark_agent_run_cancelled_activity")
    async def mark_agent_run_cancelled_activity(payload: dict) -> dict:
        cancelled_payloads.append(dict(payload))
        return {"run_id": payload["run_id"], "status": "cancelled", "summary": payload["cancel_reason"]}

    @activity.defn(name="mark_agent_run_failed_activity")
    async def mark_agent_run_failed_activity(payload: dict) -> dict:
        return {"run_id": payload["run_id"], "status": "failed", "summary": payload["failure_reason"]}

    async def scenario() -> None:
        env = await WorkflowEnvironment.start_time_skipping()
        task_queue = f"agent-test-{uuid4().hex}"
        async with Worker(
            env.client,
            task_queue=task_queue,
            workflows=[AgentRunWorkflow],
            activities=[execute_agent_graph_activity, mark_agent_run_cancelled_activity, mark_agent_run_failed_activity],
        ):
            handle = await env.client.start_workflow(
                AgentRunWorkflow.run,
                workflow_payload(task_queue),
                id=f"agent-run-test-{uuid4().hex}",
                task_queue=task_queue,
            )
            while len(execute_payloads) < 1:
                await asyncio.sleep(0.05)
            await asyncio.sleep(0.1)
            await handle.cancel()
            try:
                await handle.result()
            except WorkflowFailureError:
                pass
        await env.shutdown()

    run_async(scenario())
    assert cancelled_payloads
    assert cancelled_payloads[0]["cancel_reason"] == "Temporal workflow cancelled"


def test_agent_run_workflow_cancel_signal_uses_user_reason() -> None:
    activity_payloads: list[dict] = []
    cancelled_payloads: list[dict] = []

    @activity.defn(name="execute_agent_graph_activity")
    async def execute_agent_graph_activity(payload: dict) -> dict:
        activity_payloads.append(dict(payload))
        return {"run_id": payload["run_id"], "status": "waiting_for_user", "summary": "waiting", "staged_output_count": 0}

    @activity.defn(name="mark_agent_run_cancelled_activity")
    async def mark_agent_run_cancelled_activity(payload: dict) -> dict:
        cancelled_payloads.append(dict(payload))
        return {"run_id": payload["run_id"], "status": "cancelled", "summary": payload["cancel_reason"]}

    @activity.defn(name="mark_agent_run_failed_activity")
    async def mark_agent_run_failed_activity(payload: dict) -> dict:
        return {"run_id": payload["run_id"], "status": "failed", "summary": payload["failure_reason"]}

    async def scenario() -> None:
        env = await WorkflowEnvironment.start_time_skipping()
        task_queue = f"agent-test-{uuid4().hex}"
        async with Worker(
            env.client,
            task_queue=task_queue,
            workflows=[AgentRunWorkflow],
            activities=[execute_agent_graph_activity, mark_agent_run_cancelled_activity, mark_agent_run_failed_activity],
        ):
            handle = await env.client.start_workflow(
                AgentRunWorkflow.run,
                workflow_payload(task_queue),
                id=f"agent-run-test-{uuid4().hex}",
                task_queue=task_queue,
            )
            while len(activity_payloads) < 1:
                await asyncio.sleep(0.05)
            await handle.signal(AgentRunWorkflow.cancel_with_reason, {"cancel_reason": "User stopped from Workbench"})
            result = await handle.result()
        await env.shutdown()
        assert result["status"] == "cancelled"

    run_async(scenario())
    assert cancelled_payloads
    assert cancelled_payloads[0]["cancel_reason"] == "User stopped from Workbench"


def test_agent_run_workflow_marks_failed_after_activity_retries() -> None:
    attempts: list[dict] = []
    failed_payloads: list[dict] = []

    @activity.defn(name="execute_agent_graph_activity")
    async def execute_agent_graph_activity(payload: dict) -> dict:
        attempts.append(dict(payload))
        raise RuntimeError("permanent graph failure")

    @activity.defn(name="mark_agent_run_cancelled_activity")
    async def mark_agent_run_cancelled_activity(payload: dict) -> dict:
        return {"run_id": payload["run_id"], "status": "cancelled", "summary": payload["cancel_reason"]}

    @activity.defn(name="mark_agent_run_failed_activity")
    async def mark_agent_run_failed_activity(payload: dict) -> dict:
        failed_payloads.append(dict(payload))
        return {"run_id": payload["run_id"], "status": "failed", "summary": payload["failure_reason"]}

    async def scenario() -> None:
        env = await WorkflowEnvironment.start_time_skipping()
        task_queue = f"agent-test-{uuid4().hex}"
        payload = workflow_payload(task_queue)
        payload["activity_retry_attempts"] = 2
        async with Worker(
            env.client,
            task_queue=task_queue,
            workflows=[AgentRunWorkflow],
            activities=[execute_agent_graph_activity, mark_agent_run_cancelled_activity, mark_agent_run_failed_activity],
        ):
            result = await env.client.execute_workflow(
                AgentRunWorkflow.run,
                payload,
                id=f"agent-run-test-{uuid4().hex}",
                task_queue=task_queue,
            )
        await env.shutdown()
        assert result["status"] == "failed"

    run_async(scenario())
    assert len(attempts) == 2
    assert failed_payloads
    assert "Temporal activity failed after retries" in failed_payloads[0]["failure_reason"]


def test_agent_run_workflow_marks_failed_after_activity_timeout() -> None:
    failed_payloads: list[dict] = []

    @activity.defn(name="execute_agent_graph_activity")
    async def execute_agent_graph_activity(payload: dict) -> dict:
        await asyncio.sleep(3)
        return {"run_id": payload["run_id"], "status": "succeeded", "summary": "too late", "staged_output_count": 0}

    @activity.defn(name="mark_agent_run_cancelled_activity")
    async def mark_agent_run_cancelled_activity(payload: dict) -> dict:
        return {"run_id": payload["run_id"], "status": "cancelled", "summary": payload["cancel_reason"]}

    @activity.defn(name="mark_agent_run_failed_activity")
    async def mark_agent_run_failed_activity(payload: dict) -> dict:
        failed_payloads.append(dict(payload))
        return {"run_id": payload["run_id"], "status": "failed", "summary": payload["failure_reason"]}

    async def scenario() -> None:
        env = await WorkflowEnvironment.start_time_skipping()
        task_queue = f"agent-test-{uuid4().hex}"
        payload = workflow_payload(task_queue)
        payload["activity_start_to_close_timeout_seconds"] = 1
        payload["activity_retry_attempts"] = 1
        async with Worker(
            env.client,
            task_queue=task_queue,
            workflows=[AgentRunWorkflow],
            activities=[execute_agent_graph_activity, mark_agent_run_cancelled_activity, mark_agent_run_failed_activity],
        ):
            result = await env.client.execute_workflow(
                AgentRunWorkflow.run,
                payload,
                id=f"agent-run-test-{uuid4().hex}",
                task_queue=task_queue,
            )
        await env.shutdown()
        assert result["status"] == "failed"

    run_async(scenario())
    assert failed_payloads
    assert "Temporal activity failed after retries" in failed_payloads[0]["failure_reason"]
