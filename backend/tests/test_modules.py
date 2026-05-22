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
    assert module["mapping_rules"] == []

    hidden_from_other_workspace = client.patch(
        f"/api/workspaces/{second_workspace['id']}/projects/{project['id']}/modules/{module['id']}?actor_email=owner@qualiforge.local",
        json={"name": "Wrong workspace"},
    )
    assert hidden_from_other_workspace.status_code == 404

    updated = client.patch(
        f"/api/workspaces/{first_workspace['id']}/projects/{project['id']}/modules/{module['id']}?actor_email=owner@qualiforge.local",
        json={"name": "支付与退款", "owner": "Checkout QA"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "支付与退款"
    assert updated.json()["owner"] == "Checkout QA"

    modules = client.get(f"/api/workspaces/{first_workspace['id']}/projects/{project['id']}/modules").json()
    assert [item["id"] for item in modules] == [module["id"]]

    deleted = client.delete(
        f"/api/workspaces/{first_workspace['id']}/projects/{project['id']}/modules/{module['id']}?actor_email=owner@qualiforge.local"
    )
    assert deleted.status_code == 204
    assert client.get(f"/api/workspaces/{first_workspace['id']}/projects/{project['id']}/modules").json() == []

    audit_logs = client.get(f"/api/workspaces/{first_workspace['id']}/audit-logs").json()
    actions = [entry["action"] for entry in audit_logs]
    assert "module.created" in actions
    assert "module.updated" in actions
    assert "module.deleted" in actions


def test_module_mapping_rules_cover_supported_targets_sources_filters_and_audit() -> None:
    client = make_client()
    workspace = create_workspace(client)
    project = create_project(client, workspace["id"])
    module = create_module(client, workspace["id"], project["id"])

    examples = [
        ("directory", "backend/app/payments/**", "manual"),
        ("file", "frontend/src/payments/Checkout.tsx", "ai_repository"),
        ("api", "POST /api/payments", "ai_repository"),
        ("service", "payment-service", "ai_history"),
        ("config_key", "PAYMENT_GATEWAY_TIMEOUT", "manual"),
        ("database_migration", "migrations/*payment*", "diff_confirmation"),
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
        rule_ids.append(response.json()["id"])

    duplicate = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/modules/{module['id']}/mapping-rules?actor_email=owner@qualiforge.local",
        json={"rule_type": "keyword", "pattern": "refund", "source": "manual"},
    )
    assert duplicate.status_code == 409

    updated = client.patch(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/modules/{module['id']}/mapping-rules/{rule_ids[0]}?actor_email=owner@qualiforge.local",
        json={"pattern": "backend/app/payments/**", "source": "diff_confirmation", "confidence": 95},
    )
    assert updated.status_code == 200
    assert updated.json()["source"] == "diff_confirmation"
    assert updated.json()["confidence"] == 95

    modules = client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/modules").json()
    assert len(modules[0]["mapping_rules"]) == 7
    assert {rule["rule_type"] for rule in modules[0]["mapping_rules"]} == {item[0] for item in examples}

    diff_rules = client.get(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/mapping-rules?source=diff_confirmation"
    ).json()
    assert {rule["pattern"] for rule in diff_rules} == {"backend/app/payments/**", "migrations/*payment*"}

    api_rules = client.get(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/mapping-rules?rule_type=api&module_id={module['id']}"
    ).json()
    assert [rule["pattern"] for rule in api_rules] == ["POST /api/payments"]

    deleted = client.delete(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/modules/{module['id']}/mapping-rules/{rule_ids[-1]}?actor_email=owner@qualiforge.local"
    )
    assert deleted.status_code == 204

    rules_after_delete = client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/mapping-rules").json()
    assert len(rules_after_delete) == 6

    audit_logs = client.get(f"/api/workspaces/{workspace['id']}/audit-logs").json()
    actions = [entry["action"] for entry in audit_logs]
    assert "mapping_rule.created" in actions
    assert "mapping_rule.updated" in actions
    assert "mapping_rule.deleted" in actions
