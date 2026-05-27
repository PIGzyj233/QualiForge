from pathlib import Path

from fastapi.testclient import TestClient

from app.platform.config import Settings
from app.main import create_app


def make_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        redis_url="redis://localhost:6379/15",
        import_storage_root=str(tmp_path / "imports"),
    )
    return TestClient(create_app(settings))


def create_workspace(client: TestClient) -> dict:
    response = client.post(
        "/api/workspaces",
        json={
            "name": "Import Lab",
            "owner_email": "owner@qualiforge.local",
            "owner_display_name": "Workspace Owner",
        },
    )
    assert response.status_code == 201
    return response.json()


def add_member(client: TestClient, workspace_id: str) -> dict:
    response = client.post(
        f"/api/workspaces/{workspace_id}/members?actor_email=owner@qualiforge.local",
        json={
            "email": "member@qualiforge.local",
            "display_name": "Workspace Member",
            "role": "WorkspaceMember",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_project(client: TestClient, workspace_id: str) -> dict:
    response = client.post(
        f"/api/workspaces/{workspace_id}/projects?actor_email=owner@qualiforge.local",
        json={"name": "Checkout", "key": "CHECKOUT", "description": "Checkout service"},
    )
    assert response.status_code == 201
    return response.json()


def create_module(client: TestClient, workspace_id: str, project_id: str) -> dict:
    module = client.post(
        f"/api/workspaces/{workspace_id}/projects/{project_id}/modules?actor_email=owner@qualiforge.local",
        json={"key": "PAYMENT", "name": "支付与退款", "description": "Payment domain", "owner": "Checkout QA"},
    )
    assert module.status_code == 201
    created = module.json()
    rule = client.post(
        f"/api/workspaces/{workspace_id}/projects/{project_id}/modules/{created['id']}/mapping-rules?actor_email=owner@qualiforge.local",
        json={"rule_type": "keyword", "pattern": "refund", "source": "manual", "description": "Refund cases", "confidence": 100},
    )
    assert rule.status_code == 201
    return created


def upload_csv(client: TestClient, workspace_id: str, project_id: str, content: str) -> dict:
    response = client.post(
        f"/api/workspaces/{workspace_id}/projects/{project_id}/imports?actor_email=owner@qualiforge.local",
        files={"file": ("historical_cases.csv", content.encode("utf-8-sig"), "text/csv")},
    )
    assert response.status_code == 202, response.text
    batch_id = response.json()["id"]
    return client.get(f"/api/workspaces/{workspace_id}/projects/{project_id}/imports/{batch_id}").json()


def test_csv_upload_creates_import_batch_job_preserved_file_and_ai_drafts(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    workspace = create_workspace(client)
    project = create_project(client, workspace["id"])
    module = create_module(client, workspace["id"], project["id"])

    batch = upload_csv(
        client,
        workspace["id"],
        project["id"],
        "标题,步骤,预期结果,优先级,风险,标签,模块,Legacy ID\n"
        "Refund after payment,\"1. pay order\n2. request refund\",Refund succeeds,P1,high,\"checkout refund\",支付与退款,TC-9\n",
    )

    assert batch["status"] == "preview_ready"
    assert batch["row_count"] == 1
    assert batch["raw_rows"][0]["title"] == "Refund after payment"
    assert batch["ai_conversion_result"][0]["custom_fields"] == {"Legacy ID": "TC-9"}
    assert batch["ai_conversion_result"][0]["expected_result"] == "Refund succeeds"
    assert Path(batch["original_file_path"]).exists()

    drafts = client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/imports/{batch['id']}/drafts").json()
    assert len(drafts) == 1
    assert drafts[0]["module_id"] == module["id"]
    assert drafts[0]["steps"] == [
        {"action": "pay order", "expected": ""},
        {"action": "request refund", "expected": "Refund succeeds"},
    ]
    assert drafts[0]["tags"] == ["checkout", "refund"]

    jobs = client.get(f"/api/workspaces/{workspace['id']}/jobs").json()
    assert jobs[0]["job_type"] == "import_cases"
    assert jobs[0]["status"] == "succeeded"
    assert "Normalized 1 imported case drafts" in jobs[0]["output_summary"]


def test_case_text_import_does_not_match_path_like_mapping_rules(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    workspace = create_workspace(client)
    project = create_project(client, workspace["id"])
    module = create_module(client, workspace["id"], project["id"])
    path_only = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/modules?actor_email=owner@qualiforge.local",
        json={"key": "PATHS", "name": "Path rules", "description": "Path-only mapping", "owner": "Checkout QA"},
    )
    assert path_only.status_code == 201
    directory_rule = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/modules/{path_only.json()['id']}/mapping-rules?actor_email=owner@qualiforge.local",
        json={"rule_type": "directory", "pattern": "legacy/refund", "source": "manual", "confidence": 100},
    )
    assert directory_rule.status_code == 201

    batch = upload_csv(
        client,
        workspace["id"],
        project["id"],
        "Case Title,Steps,Expected,Tags\nRefund path mention,legacy/refund should not map by path,done,refund\n",
    )
    draft = client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/imports/{batch['id']}/drafts").json()[0]

    assert draft["module_id"] == module["id"]


def test_preview_bulk_update_review_submission_and_owner_bulk_import(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    workspace = create_workspace(client)
    add_member(client, workspace["id"])
    project = create_project(client, workspace["id"])
    module = create_module(client, workspace["id"], project["id"])
    batch = upload_csv(
        client,
        workspace["id"],
        project["id"],
        "Case Title,Steps,Expected,Priority,Risk,Tags\nCheckout smoke,\"open cart\npay\",order paid,P2,medium,smoke\n",
    )
    draft = client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/imports/{batch['id']}/drafts").json()[0]

    updated = client.patch(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/imports/{batch['id']}/drafts-bulk?actor_email=owner@qualiforge.local",
        json={
            "draft_ids": [draft["id"]],
            "module_id": module["id"],
            "priority": "P0",
            "risk": "critical",
            "tags": ["checkout", "release"],
            "custom_fields": {"suite": "regression"},
        },
    )
    assert updated.status_code == 200
    assert updated.json()[0]["priority"] == "P0"
    assert updated.json()[0]["custom_fields"] == {"suite": "regression"}

    submitted = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/imports/{batch['id']}/submit-review?actor_email=owner@qualiforge.local"
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "review_submitted"

    forbidden = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/imports/{batch['id']}/bulk-import?actor_email=member@qualiforge.local"
    )
    assert forbidden.status_code == 403

    blocked_import = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/imports/{batch['id']}/bulk-import?actor_email=owner@qualiforge.local"
    )
    assert blocked_import.status_code == 409
    assert "approved" in blocked_import.json()["detail"]

    test_cases = client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/test-cases").json()
    assert len(test_cases) == 1
    assert test_cases[0]["module_id"] == module["id"]
    assert test_cases[0]["review_status"] == "pending_review"
    assert test_cases[0]["active_draft"]["priority"] == "P0"
    assert test_cases[0]["active_draft"]["tags"] == ["checkout", "release"]
    assert test_cases[0]["active_draft"]["steps"][-1]["expected"] == "order paid"
    cycle_id = test_cases[0]["open_cycle"]["id"]

    settings = client.put(
        f"/api/workspaces/{workspace['id']}/review-settings?actor_email=owner@qualiforge.local",
        json={"allow_self_review": True, "require_review_on_case_update": True},
    )
    assert settings.status_code == 200

    approved = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/review-cycles/{cycle_id}/approve?actor_email=owner@qualiforge.local",
        json={"comment": "Approved imported baseline"},
    )
    assert approved.status_code == 201

    imported = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/imports/{batch['id']}/bulk-import?actor_email=owner@qualiforge.local"
    )
    assert imported.status_code == 200
    assert imported.json()["imported_count"] == 1
    assert imported.json()["batch"]["status"] == "imported"
    assert imported.json()["batch"]["imported_at"] is not None

    finalized_drafts = client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/imports/{batch['id']}/drafts").json()
    assert finalized_drafts[0]["status"] == "imported"

    active_cases = client.get(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/test-cases?lifecycle_status=active"
    ).json()
    assert len(active_cases) == 1
    assert active_cases[0]["review_status"] is None
    assert active_cases[0]["current_revision"]["content_snapshot"]["priority"] == "P0"
    assert active_cases[0]["current_revision"]["content_snapshot"]["tags"] == ["checkout", "release"]
    assert active_cases[0]["current_revision"]["content_snapshot"]["expected_result"] == "order paid"

    repeated = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/imports/{batch['id']}/bulk-import?actor_email=owner@qualiforge.local"
    )
    assert repeated.status_code == 409

    resubmitted = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/imports/{batch['id']}/submit-review?actor_email=owner@qualiforge.local"
    )
    assert resubmitted.status_code == 409

    audit_logs = client.get(f"/api/workspaces/{workspace['id']}/audit-logs?actor_email=owner@qualiforge.local").json()
    actions = [entry["action"] for entry in audit_logs]
    assert "import_batch.uploaded" in actions
    assert "import_draft.bulk_updated" in actions
    assert "import_batch.review_submitted" in actions
    assert "import_batch.imported" in actions
