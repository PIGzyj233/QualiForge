from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agents import AgentRun, AgentRunStatus
from app.agents.workflow_gateway import AgentWorkflowUnavailable
from app.cases.ai_suggestions import (
    AI_SUGGESTION_STALE_MINUTES,
    create_ai_suggestion_agent_run,
    execute_ai_suggestion_generation,
    parse_llm_suggestion_json,
)
from app.cases.diff_models import DiffAnalysis
from app.workspace.routes import now_utc
from test_diff_analysis import (
    OWNER,
    bind_and_sync_repository,
    create_diff_fixture_repo,
    create_module_with_rules,
    create_workspace_project,
    make_client,
)


class FakeAISuggestionWorkflowGateway:
    def __init__(self, *, fail_start: AgentWorkflowUnavailable | None = None) -> None:
        self.fail_start = fail_start
        self.started: list[dict[str, Any]] = []

    def start_ai_suggestion_run(self, **kwargs):
        if self.fail_start is not None:
            raise self.fail_start
        run = kwargs["run"]
        run.temporal_workflow_id = f"agent-run-{run.id}"
        run.current_phase = "temporal_queued"
        kwargs["db"].commit()
        self.started.append(kwargs)
        return {"summary": "AI suggestion workflow started"}


def test_parse_llm_suggestion_json_uses_final_suggestions_object() -> None:
    content = """
    {"task": "Explore repository context for diff analysis a34a5ed2f2454fa4bc058e399d6ea287 (10.2.9.6..10.3.0.0)"}
    ```json
    {"suggestions": [{"suggestion_type": "regression", "module_key": "PAYMENT"}]}
    ```
    {"debug": "trailing object from model"}
    """

    assert parse_llm_suggestion_json(content) == [{"suggestion_type": "regression", "module_key": "PAYMENT"}]


def install_fake_ai_suggestion_gateway(client: TestClient, *, fail_start: AgentWorkflowUnavailable | None = None) -> FakeAISuggestionWorkflowGateway:
    gateway = FakeAISuggestionWorkflowGateway(fail_start=fail_start)
    client.app.state.agent_workflow_gateway = gateway
    return gateway


def execute_ai_suggestion_job(client: TestClient, workspace_id: str, project_id: str, analysis_id: str, run_id: str, *, force: bool = False) -> dict[str, Any]:
    database = client.app.state.database
    database.init()
    with database.session_factory() as db:
        return execute_ai_suggestion_generation(
            db,
            settings=client.app.state.settings,
            workspace_id=workspace_id,
            project_id=project_id,
            analysis_id=analysis_id,
            run_id=run_id,
            actor_email=OWNER,
            force=force,
            model_gateway_transport=getattr(client.app.state, "model_gateway_transport", None),
        )


def successful_ai_suggestion_transport(model_calls: list[dict[str, Any]]):
    def transport(url: str, headers: dict[str, str], payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        model_calls.append({"url": url, "headers": headers, "payload": payload, "timeout_seconds": timeout_seconds})
        if payload.get("tools") and not any(message.get("role") == "tool" for message in payload.get("messages", [])):
            return {
                "id": "chatcmpl-ai-suggestions-tools",
                "model": payload["model"],
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_search_refund",
                                    "type": "function",
                                    "function": {
                                        "name": "code_search",
                                        "arguments": json.dumps(
                                            {"pattern": "refund_order", "path": ".", "max_results": 10},
                                            ensure_ascii=False,
                                        ),
                                    },
                                },
                                {
                                    "id": "call_read_checkout",
                                    "type": "function",
                                    "function": {
                                        "name": "code_read_range",
                                        "arguments": json.dumps(
                                            {"path": "src/payment/checkout.py", "start_line": 1, "end_line": 20},
                                            ensure_ascii=False,
                                        ),
                                    },
                                },
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 220, "completion_tokens": 40},
            }
        if payload.get("tools"):
            return {
                "id": "chatcmpl-ai-suggestions-tool-stop",
                "model": payload["model"],
                "choices": [{"message": {"content": "Repository exploration complete."}}],
                "usage": {"prompt_tokens": 260, "completion_tokens": 20},
            }
        content = {
            "suggestions": [
                {
                    "suggestion_type": "regression",
                    "module_key": "PAYMENT",
                    "title": "回归 PAYMENT 退款链路和配置变更",
                    "rationale": "Diff 新增 /checkout/refund 路由，并修改 payment_timeout 与 refund_enabled，需覆盖退款主路径、配置开关和回滚风险。",
                    "confidence": 96,
                    "interfaces": ["/checkout/refund"],
                    "config_keys": ["payment_timeout", "refund_enabled"],
                    "evidence": ["+@router.post('/checkout/refund')", "refund_enabled: true"],
                },
                {
                    "suggestion_type": "case_candidate",
                    "module_key": "PAYMENT",
                    "title": "验证退款接口与支付超时配置",
                    "rationale": "Diff 增加退款接口、退款表迁移和配置项，当前正式用例只覆盖支付主路径，需要候选用例补齐退款行为。",
                    "confidence": 93,
                    "interfaces": ["/checkout/refund"],
                    "config_keys": ["payment_timeout", "refund_enabled"],
                    "evidence": ["create table refunds", "+@router.post('/checkout/refund')"],
                    "steps": [
                        {"action": "调用 POST /checkout/refund 发起退款", "expected": "接口返回退款成功且不会影响原支付状态"},
                        {"action": "关闭 refund_enabled 后再次发起退款", "expected": "系统按配置拒绝或降级处理退款请求"},
                    ],
                },
            ]
        }
        return {
            "id": "chatcmpl-ai-suggestions-test",
            "model": payload["model"],
            "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
            "usage": {"prompt_tokens": 180, "completion_tokens": 120},
        }

    return transport


def create_approved_case(client: TestClient, workspace_id: str, project_id: str, module_id: str) -> dict:
    settings = client.put(
        f"/api/workspaces/{workspace_id}/review-settings?actor_email={OWNER}",
        json={"allow_self_review": True, "require_review_on_case_update": True},
    )
    assert settings.status_code == 200
    created = client.post(
        f"/api/workspaces/{workspace_id}/projects/{project_id}/test-cases?actor_email={OWNER}",
        json={
            "module_id": module_id,
            "title": "Approved checkout payment regression",
            "steps": ["Open checkout", "Pay order"],
            "expected_result": "Order is paid",
            "priority": "P1",
            "risk": "high",
            "tags": ["checkout", "payment"],
            "custom_fields": {"source": "manual"},
        },
    )
    assert created.status_code == 201
    test_case = created.json()
    submitted = client.post(
        f"/api/workspaces/{workspace_id}/projects/{project_id}/test-cases/{test_case['id']}/submit-review?actor_email={OWNER}"
    )
    assert submitted.status_code == 200
    reviewed = client.post(
        f"/api/workspaces/{workspace_id}/projects/{project_id}/test-cases/{test_case['id']}/reviews?actor_email={OWNER}",
        json={"action": "approved", "comment": "Baseline approved"},
    )
    assert reviewed.status_code == 201
    fetched = client.get(f"/api/workspaces/{workspace_id}/projects/{project_id}/test-cases/{test_case['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["lifecycle_status"] == "active"
    assert fetched.json()["current_revision"]["content_snapshot"]["title"] == "Approved checkout payment regression"
    return fetched.json()


def create_analysis_with_formal_case(tmp_path: Path, model_gateway_transport=None) -> tuple[TestClient, dict, dict, dict, dict]:
    settings_overrides = (
        {
            "model_gateway_api_base_url": "http://model-endpoint:4000/v1",
            "model_gateway_api_key": "test-model-key",
            "model_gateway_default_model": "deepseek-v4-pro",
            "model_gateway_reasoning_effort": "high",
        }
        if model_gateway_transport is not None
        else None
    )
    client = make_client(tmp_path, model_gateway_transport, settings_overrides=settings_overrides)
    workspace, project = create_workspace_project(client)
    module = create_module_with_rules(client, workspace["id"], project["id"])
    formal_case = create_approved_case(client, workspace["id"], project["id"], module["id"])
    source = create_diff_fixture_repo(tmp_path)
    repository = bind_and_sync_repository(client, workspace["id"], project["id"], source)
    response = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/diff-analyses?actor_email={OWNER}",
        json={"repository_id": repository["id"], "base_ref": "v1", "target_ref": "v2"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "succeeded"
    return client, workspace, project, formal_case, response.json()


def test_ai_suggestions_link_diff_mapping_cases_feedback_and_plan_items(tmp_path: Path) -> None:
    model_calls: list[dict[str, Any]] = []
    client, workspace, project, formal_case, analysis = create_analysis_with_formal_case(
        tmp_path,
        successful_ai_suggestion_transport(model_calls),
    )
    gateway = install_fake_ai_suggestion_gateway(client)

    generated = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/diff-analyses/{analysis['id']}/ai-suggestions?actor_email={OWNER}"
    )

    assert generated.status_code == 202
    queued = generated.json()
    assert queued["agent_run"]["temporal_workflow_id"] == f"agent-run-{queued['agent_run']['id']}"
    assert queued["suggestions"] == []
    assert len(gateway.started) == 1
    result = execute_ai_suggestion_job(client, workspace["id"], project["id"], analysis["id"], queued["agent_run"]["id"])
    assert result["status"] == "succeeded"
    status_response = client.get(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/diff-analyses/{analysis['id']}/ai-suggestions/status?actor_email={OWNER}"
    )
    assert status_response.status_code == 200
    assert model_calls[0]["url"] == "http://model-endpoint:4000/v1/chat/completions"
    assert model_calls[0]["payload"]["model"] == "deepseek-v4-pro"
    assert model_calls[0]["payload"].get("tools")
    assert any(message.get("role") == "tool" for message in model_calls[-1]["payload"]["messages"])
    suggestions = status_response.json()["suggestions"]
    regression = next(item for item in suggestions if item["suggestion_type"] == "regression")
    candidate = next(item for item in suggestions if item["suggestion_type"] == "case_candidate")

    assert regression["source_diff"]["analysis_id"] == analysis["id"]
    assert regression["source_diff"]["llm_used"] is True
    assert regression["source_diff"]["agent_run_id"]
    assert regression["source_diff"]["tool_observation_count"] >= 2
    assert regression["title"] == "回归 PAYMENT 退款链路和配置变更"
    assert "/checkout/refund" in regression["interfaces"]
    assert "payment_timeout" in regression["config_keys"]
    assert any("directory:src/payment" in item for item in regression["mapping_evidence"])
    assert formal_case["id"] in regression["related_case_ids"]
    assert formal_case["id"] in regression["selected_case_ids"]
    assert regression["rationale"]
    assert regression["confidence"] >= 90
    assert candidate["candidate_payload"]["custom_fields"]["diff_analysis_id"] == analysis["id"]
    assert candidate["candidate_payload"]["steps"][0]["action"] == "调用 POST /checkout/refund 发起退款"

    invocations = client.get(f"/api/workspaces/{workspace['id']}/ai-invocations").json()
    final_invocation = next(item for item in invocations if item["usage"] == {"prompt_tokens": 180, "completion_tokens": 120})
    assert final_invocation["provider_name"] == "deepseek"
    assert final_invocation["model_alias"] == "deepseek-v4-pro"
    tool_calls = client.get(
        f"/api/workspaces/{workspace['id']}/agent/runs/{regression['source_diff']['agent_run_id']}/tool-calls"
    ).json()
    assert {item["tool_name"] for item in tool_calls} >= {"code_search", "code_read_range"}

    updated = client.patch(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/ai-suggestions/{regression['id']}?actor_email={OWNER}",
        json={"status": "accepted", "feedback_comment": "Keep this regression item", "selected_case_ids": [formal_case["id"]]},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "accepted"
    assert updated.json()["feedback_history"][0]["comment"] == "Keep this regression item"

    locked_force = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/diff-analyses/{analysis['id']}/ai-suggestions?actor_email={OWNER}&force=true"
    )
    assert locked_force.status_code == 409

    plan_items = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/ai-suggestions/{regression['id']}/plan-items?actor_email={OWNER}",
        json={"version_ref": "v2", "test_case_ids": [formal_case["id"]]},
    )
    assert plan_items.status_code == 201
    formal_item = plan_items.json()["items"][0]
    assert formal_item["source_type"] == "formal_case"
    assert formal_item["source_id"] == formal_case["id"]
    assert formal_item["snapshot"]["title"] == formal_case["title"]
    assert regression["title"] in formal_item["rationale"]

    candidate_case = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/ai-suggestions/{candidate['id']}/candidate?actor_email={OWNER}"
    )
    assert candidate_case.status_code == 201
    created_case = candidate_case.json()["test_case"]
    assert created_case["lifecycle_status"] == "draft"
    assert created_case["active_draft"]["custom_fields"]["source"] == "ai_suggestion"

    temp_plan_item = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/ai-suggestions/{candidate['id']}/plan-items?actor_email={OWNER}",
        json={"version_ref": "v2", "include_ai_candidate": True},
    )
    assert temp_plan_item.status_code == 201
    temp_item = temp_plan_item.json()["items"][0]
    assert temp_item["source_type"] == "ai_temp"
    assert temp_item["source_id"] == candidate["id"]
    assert temp_item["snapshot"]["custom_fields"]["diff_analysis_id"] == analysis["id"]

    approved_cases = client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/test-cases?lifecycle_status=active").json()
    assert [item["id"] for item in approved_cases] == [formal_case["id"]]


def test_ai_suggestions_are_idempotent_for_same_diff_analysis(tmp_path: Path) -> None:
    model_calls: list[dict[str, Any]] = []
    client, workspace, project, _formal_case, analysis = create_analysis_with_formal_case(
        tmp_path,
        successful_ai_suggestion_transport(model_calls),
    )
    gateway = install_fake_ai_suggestion_gateway(client)

    first = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/diff-analyses/{analysis['id']}/ai-suggestions?actor_email={OWNER}"
    )
    second = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/diff-analyses/{analysis['id']}/ai-suggestions?actor_email={OWNER}"
    )

    assert first.status_code == 202
    assert second.status_code == 202
    first_job = first.json()
    second_job = second.json()
    assert first_job["agent_run"]["id"] == second_job["agent_run"]["id"]
    assert second_job["reused_running"] is True
    assert len(gateway.started) == 1
    assert model_calls == []
    execute_ai_suggestion_job(client, workspace["id"], project["id"], analysis["id"], first_job["agent_run"]["id"])
    existing = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/diff-analyses/{analysis['id']}/ai-suggestions?actor_email={OWNER}"
    )
    assert existing.status_code == 200
    first_suggestions = existing.json()["suggestions"]
    assert len(first_suggestions) >= 2
    assert len(model_calls) == 3

    forced = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/diff-analyses/{analysis['id']}/ai-suggestions?actor_email={OWNER}&force=true"
    )

    assert forced.status_code == 202
    forced_job = forced.json()
    assert forced_job["agent_run"]["id"] != first_job["agent_run"]["id"]
    execute_ai_suggestion_job(client, workspace["id"], project["id"], analysis["id"], forced_job["agent_run"]["id"], force=True)
    regenerated = client.get(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/diff-analyses/{analysis['id']}/ai-suggestions/status?actor_email={OWNER}"
    ).json()["suggestions"]
    assert [item["id"] for item in regenerated] != [item["id"] for item in first_suggestions]
    assert len(model_calls) == 6


def test_ai_suggestion_temporal_start_failure_marks_run_failed(tmp_path: Path) -> None:
    client, workspace, project, _formal_case, analysis = create_analysis_with_formal_case(
        tmp_path,
        successful_ai_suggestion_transport([]),
    )
    install_fake_ai_suggestion_gateway(client, fail_start=AgentWorkflowUnavailable("Temporal unavailable: test"))

    response = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/diff-analyses/{analysis['id']}/ai-suggestions?actor_email={OWNER}"
    )

    assert response.status_code == 503
    database = client.app.state.database
    database.init()
    with database.session_factory() as db:
        run = db.scalar(select(AgentRun).where(AgentRun.trigger_type == "ai_suggestion"))
        assert run is not None
        assert run.status == AgentRunStatus.failed.value
        assert run.current_phase == "temporal_unavailable"
        assert "Temporal unavailable" in run.failure_reason


def test_stale_sync_ai_suggestion_run_is_failed_and_replaced(tmp_path: Path) -> None:
    client, workspace, project, _formal_case, analysis = create_analysis_with_formal_case(
        tmp_path,
        successful_ai_suggestion_transport([]),
    )
    gateway = install_fake_ai_suggestion_gateway(client)
    database = client.app.state.database
    database.init()
    with database.session_factory() as db:
        analysis_model = db.get(DiffAnalysis, analysis["id"])
        assert analysis_model is not None
        stale = create_ai_suggestion_agent_run(db, analysis_model, OWNER)
        stale.status = AgentRunStatus.running.value
        stale.current_phase = "ai_suggestion_code_tools"
        stale.started_at = now_utc() - timedelta(minutes=AI_SUGGESTION_STALE_MINUTES + 1)
        db.commit()
        stale_id = stale.id

    status_response = client.get(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/diff-analyses/{analysis['id']}/ai-suggestions/status?actor_email={OWNER}"
    )

    assert status_response.status_code == 200
    stale_status = status_response.json()["agent_run"]
    assert stale_status["id"] == stale_id
    assert stale_status["status"] == "failed"
    assert stale_status["current_phase"] == "stale_running"

    queued = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/diff-analyses/{analysis['id']}/ai-suggestions?actor_email={OWNER}"
    )

    assert queued.status_code == 202
    assert queued.json()["agent_run"]["id"] != stale_id
    assert len(gateway.started) == 1


def test_ai_suggestion_temporal_worker_registration() -> None:
    from app.agent_worker import execute_ai_suggestion_generation_activity as registered_activity
    from app.agents.workflows import AISuggestionWorkflow
    from app.cases.ai_suggestions import execute_ai_suggestion_generation_activity

    assert AISuggestionWorkflow.__name__ == "AISuggestionWorkflow"
    assert registered_activity is execute_ai_suggestion_generation_activity
