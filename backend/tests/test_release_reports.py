from __future__ import annotations

from pathlib import Path

from test_ai_suggestions import create_approved_case
from test_diff_analysis import OWNER, create_module_with_rules, create_workspace_project, make_client


def test_release_report_draft_decision_markdown_and_audit(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    workspace, project = create_workspace_project(client)
    module = create_module_with_rules(client, workspace["id"], project["id"])
    formal_case = create_approved_case(client, workspace["id"], project["id"], module["id"])
    plan = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/plans?actor_email={OWNER}",
        json={"name": "Release report plan", "plan_type": "release", "version_ref": "v4", "scope_summary": "Checkout release scope"},
    ).json()
    item = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/plans/{plan['id']}/items?actor_email={OWNER}",
        json={"source_type": "formal_case", "source_id": formal_case["id"], "rationale": "Payment gate"},
    ).json()
    executed = client.patch(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/plans/{plan['id']}/items/{item['id']}/execution?actor_email=runner@qualiforge.local",
        json={
            "status": "failed",
            "assignee_email": "qa@qualiforge.local",
            "actual_result": "Checkout returned HTTP 500.",
            "failure_reason": "Payment callback timeout.",
            "defect_links": ["https://bugs.local/QUALI-42"],
        },
    )
    assert executed.status_code == 200

    draft = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/plans/{plan['id']}/reports/draft?actor_email={OWNER}"
    )
    assert draft.status_code == 201
    report = draft.json()
    assert report["status"] == "draft"
    assert report["release_suggestion"] == "hold_release"
    assert report["release_decision"] == "pending_owner_confirmation"
    assert set(report["sections"]) == {
        "summary",
        "version_diff",
        "scope",
        "execution_statistics",
        "failed_blocked_items",
        "risk_assessment",
        "ai_notes",
        "release_decision",
        "appendix",
    }
    assert report["sections"]["execution_statistics"]["counts"]["failed"] == 1
    assert report["sections"]["failed_blocked_items"][0]["defect_links"] == ["https://bugs.local/QUALI-42"]
    assert "AI draft summary" in report["ai_notes"][0]

    listed = client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/plans/{plan['id']}/reports")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == report["id"]

    confirmed = client.patch(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/reports/{report['id']}/decision?actor_email={OWNER}",
        json={"release_decision": "hold_release", "decision_comment": "Do not release until QUALI-42 is fixed."},
    )
    assert confirmed.status_code == 200
    confirmed_payload = confirmed.json()
    assert confirmed_payload["status"] == "confirmed"
    assert confirmed_payload["confirmed_by"] == OWNER
    assert confirmed_payload["sections"]["release_decision"]["current_decision"] == "hold_release"

    markdown = client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/reports/{report['id']}/markdown")
    assert markdown.status_code == 200
    assert "## Summary" in markdown.text
    assert "## Version & Diff" in markdown.text
    assert "## Failed / Blocked Items" in markdown.text
    assert "## Release Decision" in markdown.text
    assert "Do not release until QUALI-42 is fixed." in markdown.text

    audit_actions = [entry["action"] for entry in client.get(f"/api/workspaces/{workspace['id']}/audit-logs").json()]
    assert "release_report.draft_generated" in audit_actions
    assert "release_report.decision_confirmed" in audit_actions
