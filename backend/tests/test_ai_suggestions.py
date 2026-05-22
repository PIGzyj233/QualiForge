from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from test_diff_analysis import (
    OWNER,
    bind_and_sync_repository,
    create_diff_fixture_repo,
    create_module_with_rules,
    create_workspace_project,
    make_client,
)


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
    assert fetched.json()["status"] == "approved"
    return fetched.json()


def create_analysis_with_formal_case(tmp_path: Path) -> tuple[TestClient, dict, dict, dict, dict]:
    client = make_client(tmp_path)
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
    client, workspace, project, formal_case, analysis = create_analysis_with_formal_case(tmp_path)

    generated = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/diff-analyses/{analysis['id']}/ai-suggestions?actor_email={OWNER}"
    )

    assert generated.status_code == 201
    suggestions = generated.json()
    regression = next(item for item in suggestions if item["suggestion_type"] == "regression")
    candidate = next(item for item in suggestions if item["suggestion_type"] == "case_candidate")

    assert regression["source_diff"]["analysis_id"] == analysis["id"]
    assert "/checkout/refund" in regression["interfaces"]
    assert "payment_timeout" in regression["config_keys"]
    assert any("directory:src/payment" in item for item in regression["mapping_evidence"])
    assert formal_case["id"] in regression["related_case_ids"]
    assert formal_case["id"] in regression["selected_case_ids"]
    assert regression["rationale"]
    assert regression["confidence"] >= 90
    assert candidate["candidate_payload"]["custom_fields"]["diff_analysis_id"] == analysis["id"]

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
    assert "Run PAYMENT regression" in formal_item["rationale"]

    candidate_case = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/ai-suggestions/{candidate['id']}/candidate?actor_email={OWNER}"
    )
    assert candidate_case.status_code == 201
    created_case = candidate_case.json()["test_case"]
    assert created_case["status"] == "draft"
    assert created_case["custom_fields"]["source"] == "ai_suggestion"

    temp_plan_item = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/ai-suggestions/{candidate['id']}/plan-items?actor_email={OWNER}",
        json={"version_ref": "v2", "include_ai_candidate": True},
    )
    assert temp_plan_item.status_code == 201
    temp_item = temp_plan_item.json()["items"][0]
    assert temp_item["source_type"] == "ai_temp"
    assert temp_item["source_id"] == candidate["id"]
    assert temp_item["snapshot"]["custom_fields"]["diff_analysis_id"] == analysis["id"]

    approved_cases = client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/test-cases?status=approved").json()
    assert [item["id"] for item in approved_cases] == [formal_case["id"]]


def test_ai_suggestions_are_idempotent_for_same_diff_analysis(tmp_path: Path) -> None:
    client, workspace, project, _formal_case, analysis = create_analysis_with_formal_case(tmp_path)

    first = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/diff-analyses/{analysis['id']}/ai-suggestions?actor_email={OWNER}"
    )
    second = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/diff-analyses/{analysis['id']}/ai-suggestions?actor_email={OWNER}"
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert [item["id"] for item in second.json()] == [item["id"] for item in first.json()]
