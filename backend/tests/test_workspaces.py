from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_client() -> TestClient:
    settings = Settings(database_url="sqlite+pysqlite:///:memory:", redis_url="redis://localhost:6379/15")
    return TestClient(create_app(settings))


def create_workspace(client: TestClient, name: str = "QA Lab") -> dict:
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


def test_workspace_owner_can_create_and_switch_workspaces() -> None:
    client = make_client()
    first = create_workspace(client, "QA Lab")
    second = create_workspace(client, "Release Lab")

    response = client.get("/api/workspaces?actor_email=owner@qualiforge.local")

    assert response.status_code == 200
    workspace_ids = {workspace["id"] for workspace in response.json()}
    assert {first["id"], second["id"]} <= workspace_ids


def test_workspace_members_can_be_added_removed_and_audited() -> None:
    client = make_client()
    workspace = create_workspace(client)

    added = client.post(
        f"/api/workspaces/{workspace['id']}/members?actor_email=owner@qualiforge.local",
        json={
            "email": "tester@qualiforge.local",
            "display_name": "Tester",
            "role": "WorkspaceMember",
        },
    )
    assert added.status_code == 201
    member_id = added.json()["id"]

    members = client.get(f"/api/workspaces/{workspace['id']}/members")
    assert [member["email"] for member in members.json()] == [
        "owner@qualiforge.local",
        "tester@qualiforge.local",
    ]

    removed = client.delete(
        f"/api/workspaces/{workspace['id']}/members/{member_id}?actor_email=owner@qualiforge.local"
    )
    assert removed.status_code == 204

    audit_logs = client.get(f"/api/workspaces/{workspace['id']}/audit-logs").json()
    actions = [entry["action"] for entry in audit_logs]
    assert "member.added" in actions
    assert "member.removed" in actions


def test_projects_are_workspace_scoped_and_audited() -> None:
    client = make_client()
    first_workspace = create_workspace(client, "QA Lab")
    second_workspace = create_workspace(client, "Release Lab")

    created = client.post(
        f"/api/workspaces/{first_workspace['id']}/projects?actor_email=owner@qualiforge.local",
        json={"name": "Checkout", "key": "CHECKOUT", "description": "Checkout regression surface"},
    )
    assert created.status_code == 201
    project = created.json()
    assert project["workspace_id"] == first_workspace["id"]

    hidden_from_other_workspace = client.patch(
        f"/api/workspaces/{second_workspace['id']}/projects/{project['id']}?actor_email=owner@qualiforge.local",
        json={"name": "Wrong workspace update"},
    )
    assert hidden_from_other_workspace.status_code == 404

    updated = client.patch(
        f"/api/workspaces/{first_workspace['id']}/projects/{project['id']}?actor_email=owner@qualiforge.local",
        json={"name": "Checkout Release", "description": "Updated scope"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Checkout Release"

    first_projects = client.get(f"/api/workspaces/{first_workspace['id']}/projects").json()
    second_projects = client.get(f"/api/workspaces/{second_workspace['id']}/projects").json()
    assert [item["id"] for item in first_projects] == [project["id"]]
    assert second_projects == []

    audit_logs = client.get(f"/api/workspaces/{first_workspace['id']}/audit-logs").json()
    assert [entry["action"] for entry in audit_logs[:2]] == ["project.updated", "project.created"]

