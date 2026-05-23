from __future__ import annotations

from pathlib import Path

from test_ai_suggestions import create_approved_case
from test_diff_analysis import OWNER, create_module_with_rules, create_workspace_project, make_client


def test_test_plan_types_items_snapshots_and_audit(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    workspace, project = create_workspace_project(client)
    module = create_module_with_rules(client, workspace["id"], project["id"])
    formal_case = create_approved_case(client, workspace["id"], project["id"], module["id"])

    plan_ids: dict[str, str] = {}
    for plan_type in ["release", "regression", "smoke", "feature", "custom"]:
        response = client.post(
            f"/api/workspaces/{workspace['id']}/projects/{project['id']}/plans?actor_email={OWNER}",
            json={
                "name": f"{plan_type.title()} plan v2",
                "plan_type": plan_type,
                "scope_summary": "Checkout payment and refund scope",
                "version_ref": "v2",
                "owner_email": "lead@qualiforge.local",
            },
        )
        assert response.status_code == 201
        payload = response.json()
        assert payload["plan_type"] == plan_type
        assert payload["status"] == "draft"
        assert payload["version_ref"] == "v2"
        assert payload["owner_email"] == "lead@qualiforge.local"
        assert payload["final_conclusion"] == ""
        plan_ids[plan_type] = payload["id"]

    release_plan_id = plan_ids["release"]
    formal_item = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/plans/{release_plan_id}/items?actor_email={OWNER}",
        json={
            "source_type": "formal_case",
            "source_id": formal_case["id"],
            "rationale": "Baseline payment regression is in release scope",
        },
    )
    assert formal_item.status_code == 201
    formal_payload = formal_item.json()
    assert formal_payload["source_type"] == "formal_case"
    assert formal_payload["status"] == "not_run"
    assert formal_payload["assignee_email"] == ""
    assert formal_payload["executed_by"] is None
    assert formal_payload["executed_at"] is None
    assert formal_payload["title"] == formal_case["title"]
    assert formal_payload["snapshot"]["title"] == formal_case["title"]
    assert formal_payload["snapshot"]["revision"] == formal_case["current_revision_number"]

    changed_case = client.patch(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/test-cases/{formal_case['id']}?actor_email={OWNER}",
        json={"title": "Changed after plan snapshot"},
    )
    assert changed_case.status_code == 200
    assert changed_case.json()["title"] == "Changed after plan snapshot"

    manual_item = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/plans/{release_plan_id}/items?actor_email={OWNER}",
        json={
            "source_type": "manual",
            "title": "Manual payment observability check",
            "snapshot": {"steps": ["Open dashboard", "Verify payment metrics"]},
            "rationale": "Manual temporary release check",
        },
    )
    assert manual_item.status_code == 201
    ai_temp_item = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/plans/{release_plan_id}/items?actor_email={OWNER}",
        json={
            "source_type": "ai_temp",
            "source_id": "ai-suggestion-1",
            "title": "AI refund edge case",
            "snapshot": {"code_paths": ["src/payment/checkout.py"], "interfaces": ["/checkout/refund"]},
            "rationale": "Temporary AI suggestion",
        },
    )
    assert ai_temp_item.status_code == 201

    items = client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/plans/{release_plan_id}/items").json()
    assert [item["source_type"] for item in items] == ["formal_case", "manual", "ai_temp"]
    assert items[0]["snapshot"]["title"] == formal_case["title"]
    assert items[0]["title"] == formal_case["title"]
    assert items[1]["snapshot"]["steps"] == ["Open dashboard", "Verify payment metrics"]
    assert items[2]["snapshot"]["interfaces"] == ["/checkout/refund"]

    audit_actions = [entry["action"] for entry in client.get(f"/api/workspaces/{workspace['id']}/audit-logs").json()]
    assert "test_plan.created" in audit_actions
    assert audit_actions.count("plan_item.added") >= 3


def test_only_approved_formal_cases_can_be_added_to_plan(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    workspace, project = create_workspace_project(client)
    draft = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/test-cases?actor_email={OWNER}",
        json={
            "title": "Draft checkout candidate",
            "steps": ["Open checkout"],
            "expected_result": "Checkout opens",
            "priority": "P2",
            "risk": "medium",
            "tags": [],
            "custom_fields": {},
        },
    ).json()
    plan = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/plans?actor_email={OWNER}",
        json={"name": "Release plan v2", "plan_type": "release", "version_ref": "v2"},
    ).json()

    response = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/plans/{plan['id']}/items?actor_email={OWNER}",
        json={"source_type": "formal_case", "source_id": draft["id"], "rationale": "Should not be accepted"},
    )

    assert response.status_code == 409
    assert "active formal cases" in response.json()["detail"]


def test_plan_item_execution_result_evidence_and_filters(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    workspace, project = create_workspace_project(client)
    module = create_module_with_rules(client, workspace["id"], project["id"])
    formal_case = create_approved_case(client, workspace["id"], project["id"], module["id"])
    plan = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/plans?actor_email={OWNER}",
        json={"name": "Release plan v3", "plan_type": "release", "version_ref": "v3"},
    ).json()
    item = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/plans/{plan['id']}/items?actor_email={OWNER}",
        json={"source_type": "formal_case", "source_id": formal_case["id"], "rationale": "Payment release gate"},
    ).json()

    assigned = client.patch(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/plans/{plan['id']}/items/{item['id']}/execution?actor_email={OWNER}",
        json={
            "status": "not_run",
            "assignee_email": "qa@qualiforge.local",
            "actual_result": "",
            "failure_reason": "",
            "defect_links": [],
        },
    )
    assert assigned.status_code == 200
    assert assigned.json()["assignee_email"] == "qa@qualiforge.local"
    assert assigned.json()["executed_at"] is None

    executed = client.patch(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/plans/{plan['id']}/items/{item['id']}/execution?actor_email=runner@qualiforge.local",
        json={
            "status": "failed",
            "assignee_email": "qa@qualiforge.local",
            "actual_result": "Checkout returned HTTP 500 after payment authorization.",
            "failure_reason": "Payment callback timeout.",
            "defect_links": [" https://bugs.local/QUALI-42 ", "https://bugs.local/QUALI-42", "https://bugs.local/QUALI-43"],
        },
    )
    assert executed.status_code == 200
    execution_payload = executed.json()
    assert execution_payload["status"] == "failed"
    assert execution_payload["actual_result"].startswith("Checkout returned")
    assert execution_payload["failure_reason"] == "Payment callback timeout."
    assert execution_payload["defect_links"] == ["https://bugs.local/QUALI-42", "https://bugs.local/QUALI-43"]
    assert execution_payload["executed_by"] == "runner@qualiforge.local"
    assert execution_payload["executed_at"]

    evidence = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/plans/{plan['id']}/items/{item['id']}/evidence?actor_email=runner@qualiforge.local",
        data={"note": "Failure screenshot"},
        files={"file": ("failure.png", b"fake-png", "image/png")},
    )
    assert evidence.status_code == 201
    evidence_payload = evidence.json()
    assert evidence_payload["evidence"][0]["file_name"] == "failure.png"
    assert evidence_payload["evidence"][0]["content_type"] == "image/png"
    assert evidence_payload["evidence"][0]["note"] == "Failure screenshot"
    assert evidence_payload["evidence"][0]["uploaded_by"] == "runner@qualiforge.local"

    failed_items = client.get(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/plans/{plan['id']}/items",
        params={"status": ["failed"], "assignee_email": "qa@qualiforge.local"},
    )
    assert failed_items.status_code == 200
    assert [row["id"] for row in failed_items.json()] == [item["id"]]
    blocked_items = client.get(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/plans/{plan['id']}/items",
        params={"status": ["blocked"]},
    )
    assert blocked_items.status_code == 200
    assert blocked_items.json() == []

    updated_plan = client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/plans").json()[0]
    assert updated_plan["status"] == "in_progress"

    audit_actions = [entry["action"] for entry in client.get(f"/api/workspaces/{workspace['id']}/audit-logs").json()]
    assert "plan_item.execution_updated" in audit_actions
    assert "plan_item.evidence_uploaded" in audit_actions
