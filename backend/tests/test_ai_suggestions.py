from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from test_diff_analysis import (
    OWNER,
    bind_and_sync_repository,
    create_diff_fixture_repo,
    create_module_with_rules,
    create_workspace_project,
    make_client,
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

    generated = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/diff-analyses/{analysis['id']}/ai-suggestions?actor_email={OWNER}"
    )

    assert generated.status_code == 201
    assert model_calls[0]["url"] == "http://model-endpoint:4000/v1/chat/completions"
    assert model_calls[0]["payload"]["model"] == "deepseek-v4-pro"
    assert model_calls[0]["payload"].get("tools")
    assert any(message.get("role") == "tool" for message in model_calls[-1]["payload"]["messages"])
    suggestions = generated.json()
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
    assert invocations[0]["provider_name"] == "deepseek"
    assert invocations[0]["model_alias"] == "deepseek-v4-pro"
    assert invocations[0]["usage"] == {"prompt_tokens": 180, "completion_tokens": 120}
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

    first = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/diff-analyses/{analysis['id']}/ai-suggestions?actor_email={OWNER}"
    )
    second = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/diff-analyses/{analysis['id']}/ai-suggestions?actor_email={OWNER}"
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert [item["id"] for item in second.json()] == [item["id"] for item in first.json()]
    assert len(model_calls) == 3

    forced = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/diff-analyses/{analysis['id']}/ai-suggestions?actor_email={OWNER}&force=true"
    )

    assert forced.status_code == 201
    assert [item["id"] for item in forced.json()] != [item["id"] for item in first.json()]
    assert len(model_calls) == 6
