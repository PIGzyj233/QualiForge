from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_client() -> TestClient:
    settings = Settings(database_url="sqlite+pysqlite:///:memory:", redis_url="redis://localhost:6379/15")
    return TestClient(create_app(settings))


def create_workspace(client: TestClient, name: str = "Module Lab") -> dict:
    response = client.post(
        "/api/workspaces",
        json={
            "name": name,
            "owner_email": "owner@qualiforge.local",
            "owner_display_name": "Workspace Owner",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_project(client: TestClient, workspace_id: str, key: str = "CHECKOUT") -> dict:
    response = client.post(
        f"/api/workspaces/{workspace_id}/projects?actor_email=owner@qualiforge.local",
        json={"name": "Checkout", "key": key, "description": "Checkout service"},
    )
    assert response.status_code == 201
    return response.json()


def create_module(client: TestClient, workspace_id: str, project_id: str) -> dict:
    response = client.post(
        f"/api/workspaces/{workspace_id}/projects/{project_id}/modules?actor_email=owner@qualiforge.local",
        json={
            "key": "PAYMENT",
            "name": "支付域",
            "description": "Checkout payment and refund behavior",
            "owner": "QA Payment",
            "keywords": ["payment", "refund", " payment "],
        },
    )
    assert response.status_code == 201
    return response.json()


def test_project_modules_can_be_created_edited_listed_deleted_and_audited() -> None:
    client = make_client()
    first_workspace = create_workspace(client, "Module Lab")
    second_workspace = create_workspace(client, "Other Lab")
    project = create_project(client, first_workspace["id"])

    module = create_module(client, first_workspace["id"], project["id"])
    assert module["key"] == "PAYMENT"
    assert module["keywords"] == ["payment", "refund"]
    assert module["mapping_rules"] == []

    hidden_from_other_workspace = client.patch(
        f"/api/workspaces/{second_workspace['id']}/projects/{project['id']}/modules/{module['id']}?actor_email=owner@qualiforge.local",
        json={"name": "Wrong workspace"},
    )
    assert hidden_from_other_workspace.status_code == 404

    updated = client.patch(
        f"/api/workspaces/{first_workspace['id']}/projects/{project['id']}/modules/{module['id']}?actor_email=owner@qualiforge.local",
        json={"name": "支付与退款", "owner": "Checkout QA", "keywords": ["checkout", "refund"]},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "支付与退款"
    assert updated.json()["owner"] == "Checkout QA"
    assert updated.json()["keywords"] == ["checkout", "refund"]

    duplicate_code = client.post(
        f"/api/workspaces/{first_workspace['id']}/projects/{project['id']}/modules?actor_email=owner@qualiforge.local",
        json={"name": "支付备用域", "code": "PAYMENT"},
    )
    assert duplicate_code.status_code == 409

    modules = client.get(f"/api/workspaces/{first_workspace['id']}/projects/{project['id']}/modules").json()
    assert [item["id"] for item in modules] == [module["id"]]
    assert modules[0]["keywords"] == ["checkout", "refund"]

    tree = client.get(f"/api/workspaces/{first_workspace['id']}/projects/{project['id']}/modules/tree").json()
    assert tree[0]["keywords"] == ["checkout", "refund"]

    deleted = client.delete(
        f"/api/workspaces/{first_workspace['id']}/projects/{project['id']}/modules/{module['id']}?actor_email=owner@qualiforge.local"
    )
    assert deleted.status_code == 204
    assert client.get(f"/api/workspaces/{first_workspace['id']}/projects/{project['id']}/modules").json() == []

    audit_logs = client.get(f"/api/workspaces/{first_workspace['id']}/audit-logs?actor_email=owner@qualiforge.local").json()
    actions = [entry["action"] for entry in audit_logs]
    assert "module.created" in actions
    assert "module.updated" in actions
    assert "module.deleted" in actions


def test_module_mapping_rules_cover_supported_targets_sources_filters_and_audit() -> None:
    client = make_client()
    workspace = create_workspace(client)
    project = create_project(client, workspace["id"])
    module = create_module(client, workspace["id"], project["id"])
    repository = client.post(
        f"/api/workspaces/{workspace['id']}/repositories?actor_email=owner@qualiforge.local",
        json={
            "project_id": project["id"],
            "name": "Checkout Repo",
            "remote_url": "https://example.invalid/checkout.git",
            "default_branch": "main",
        },
    )
    assert repository.status_code == 201
    repository_id = repository.json()["id"]

    examples = [
        ("directory", "backend/app/payments/**", "manual"),
        ("file", "frontend/src/payments/Checkout.tsx", "ai_repository"),
        ("api", "POST /api/payments", "ai_repository"),
        ("service", "payment-service", "ai_history"),
        ("command", "qualiforge payments sync", "manual"),
        ("library_api", "payments.capture", "ai_repository"),
        ("symbol", "PaymentProcessor", "ai_repository"),
        ("package", "app.payments", "manual"),
        ("build_target", "//payments:service", "manual"),
        ("config_key", "PAYMENT_GATEWAY_TIMEOUT", "manual"),
        ("database_migration", "migrations/*payment*", "diff_confirmation"),
        ("protocol", "HTTP/2", "manual"),
        ("transport", "WebSocket", "manual"),
        ("format", "JSON", "manual"),
        ("codec", "H264", "manual"),
        ("media_pipeline", "transcode payment-demo clips", "manual"),
        ("asset_fixture", "fixtures/payments/**", "manual"),
        ("keyword", "refund", "ai_history"),
    ]
    rule_ids = []
    for rule_type, pattern, source in examples:
        response = client.post(
            f"/api/workspaces/{workspace['id']}/projects/{project['id']}/modules/{module['id']}/mapping-rules?actor_email=owner@qualiforge.local",
            json={
                "rule_type": rule_type,
                "pattern": pattern,
                "source": source,
                "description": f"{rule_type} mapping",
                "confidence": 88,
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["relationship"] == "primary"
        assert body["status"] == "active"
        assert body["ai_confidence"] == 0
        assert body["verified_by"] == "owner@qualiforge.local"
        assert body["verified_at"] is not None
        rule_ids.append(response.json()["id"])

    scoped_rule = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/modules/{module['id']}/mapping-rules?actor_email=owner@qualiforge.local",
        json={
            "repository_id": repository_id,
            "rule_type": "file",
            "pattern": "backend/app/payments/repository_scoped.py",
            "source": "ai_repository",
            "relationship": "related",
            "status": "stale",
            "ai_confidence": 72,
            "confidence": 66,
            "description": "Repository scoped stale evidence",
            "evidence_refs": [
                {
                    "type": "file",
                    "repository_id": repository_id,
                    "ref": "main",
                    "path": "backend/app/payments/repository_scoped.py",
                    "reason": "payment repository adapter",
                }
            ],
            "conditions": {"platform": "backend"},
            "case_sensitive": True,
            "stale_reason": "file moved during refactor",
        },
    )
    assert scoped_rule.status_code == 201
    scoped_body = scoped_rule.json()
    assert scoped_body["repository_id"] == repository_id
    assert scoped_body["relationship"] == "related"
    assert scoped_body["status"] == "stale"
    assert scoped_body["ai_confidence"] == 72
    assert scoped_body["confidence"] == 66
    assert scoped_body["evidence_refs"][0]["path"] == "backend/app/payments/repository_scoped.py"
    assert scoped_body["conditions"] == {"platform": "backend"}
    assert scoped_body["case_sensitive"] is True

    archived_rule = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/modules/{module['id']}/mapping-rules?actor_email=owner@qualiforge.local",
        json={
            "rule_type": "keyword",
            "pattern": "legacy-refund",
            "source": "manual",
            "status": "archived",
            "relationship": "evidence",
            "confidence": 20,
        },
    )
    assert archived_rule.status_code == 201

    duplicate = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/modules/{module['id']}/mapping-rules?actor_email=owner@qualiforge.local",
        json={"rule_type": "keyword", "pattern": "refund", "source": "manual"},
    )
    assert duplicate.status_code == 409

    updated = client.patch(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/modules/{module['id']}/mapping-rules/{rule_ids[0]}?actor_email=owner@qualiforge.local",
        json={"pattern": "backend/app/payments/**", "source": "diff_confirmation", "confidence": 95, "relationship": "dependency"},
    )
    assert updated.status_code == 200
    assert updated.json()["source"] == "diff_confirmation"
    assert updated.json()["relationship"] == "dependency"
    assert updated.json()["confidence"] == 95

    modules = client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/modules").json()
    assert len(modules[0]["mapping_rules"]) == len(examples)
    assert {rule["rule_type"] for rule in modules[0]["mapping_rules"]} == {item[0] for item in examples}

    all_module_rules = client.get(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/modules?mapping_rule_status=all"
    ).json()
    assert len(all_module_rules[0]["mapping_rules"]) == len(examples) + 2

    diff_rules = client.get(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/mapping-rules?source=diff_confirmation"
    ).json()
    assert {rule["pattern"] for rule in diff_rules} == {"backend/app/payments/**", "migrations/*payment*"}

    stale_rules = client.get(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/mapping-rules?status=stale&repository_id={repository_id}&relationship=related"
    ).json()
    assert [rule["id"] for rule in stale_rules] == [scoped_body["id"]]

    all_rules = client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/mapping-rules?status=all").json()
    assert len(all_rules) == len(examples) + 2

    api_rules = client.get(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/mapping-rules?rule_type=api&module_id={module['id']}"
    ).json()
    assert [rule["pattern"] for rule in api_rules] == ["POST /api/payments"]

    deleted = client.delete(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/modules/{module['id']}/mapping-rules/{rule_ids[-1]}?actor_email=owner@qualiforge.local"
    )
    assert deleted.status_code == 204

    rules_after_delete = client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/mapping-rules").json()
    assert len(rules_after_delete) == len(examples) - 1

    audit_logs = client.get(f"/api/workspaces/{workspace['id']}/audit-logs?actor_email=owner@qualiforge.local").json()
    actions = [entry["action"] for entry in audit_logs]
    assert "mapping_rule.created" in actions
    assert "mapping_rule.updated" in actions
    assert "mapping_rule.deleted" in actions
    mapping_create = next(entry for entry in audit_logs if entry["action"] == "mapping_rule.created")
    assert "evidence_count" in mapping_create["after"]


def test_module_tree_archive_reference_guard_and_descendant_case_filter() -> None:
    client = make_client()
    workspace = create_workspace(client, "Tree Lab")
    project = create_project(client, workspace["id"])
    root = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/modules?actor_email=owner@qualiforge.local",
        json={"name": "操控", "code": "CTRL", "description": "Input control", "owner": "QA"},
    ).json()
    keyboard = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/modules?actor_email=owner@qualiforge.local",
        json={"name": "键鼠", "code": "CTRL_KM", "parent_id": root["id"], "description": "Keyboard and mouse", "owner": "QA"},
    ).json()
    gamepad = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/modules?actor_email=owner@qualiforge.local",
        json={"name": "手柄", "code": "CTRL_PAD", "parent_id": root["id"], "description": "Gamepad", "owner": "QA"},
    ).json()

    assert root["path"] == "cao-kong"
    assert keyboard["path_label"] == "操控 / 键鼠"

    tree = client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/modules/tree").json()
    assert tree[0]["id"] == root["id"]
    assert {child["id"] for child in tree[0]["children"]} == {keyboard["id"], gamepad["id"]}

    case = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/test-cases?actor_email=owner@qualiforge.local",
        json={
            "module_id": keyboard["id"],
            "title": "Keyboard shortcut works",
            "steps": ["Press shortcut"],
            "expected_result": "Action runs",
            "priority": "P2",
            "risk": "medium",
            "tags": ["keyboard"],
            "custom_fields": {},
        },
    )
    assert case.status_code == 201
    filtered = client.get(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/test-cases?module_id={root['id']}"
    ).json()
    assert [item["id"] for item in filtered] == [case.json()["id"]]

    referenced_delete = client.delete(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/modules/{keyboard['id']}?actor_email=owner@qualiforge.local"
    )
    assert referenced_delete.status_code == 409

    archived = client.patch(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/modules/{root['id']}?actor_email=owner@qualiforge.local",
        json={"status": "archived"},
    )
    assert archived.status_code == 200
    assert client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/modules").json() == []
    archived_modules = client.get(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/modules?include_archived_modules=true"
    ).json()
    assert {module["status"] for module in archived_modules} == {"archived"}
