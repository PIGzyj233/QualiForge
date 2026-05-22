from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_client() -> TestClient:
    settings = Settings(database_url="sqlite+pysqlite:///:memory:", redis_url="redis://localhost:6379/15")
    return TestClient(create_app(settings))


def create_workspace(client: TestClient) -> dict:
    response = client.post(
        "/api/workspaces",
        json={
            "name": "Review Lab",
            "owner_email": "owner@qualiforge.local",
            "owner_display_name": "Workspace Owner",
        },
    )
    assert response.status_code == 201
    return response.json()


def add_member(client: TestClient, workspace_id: str, email: str = "author@qualiforge.local") -> dict:
    response = client.post(
        f"/api/workspaces/{workspace_id}/members?actor_email=owner@qualiforge.local",
        json={"email": email, "display_name": "Author", "role": "WorkspaceMember"},
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


def create_case(client: TestClient, workspace_id: str, project_id: str, actor: str = "author@qualiforge.local") -> dict:
    response = client.post(
        f"/api/workspaces/{workspace_id}/projects/{project_id}/test-cases?actor_email={actor}",
        json={
            "title": "Checkout payment succeeds",
            "steps": ["Open checkout", "Pay order"],
            "expected_result": "Order is paid",
            "priority": "P1",
            "risk": "high",
            "tags": ["checkout"],
            "custom_fields": {"source": "manual"},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def submit_case(client: TestClient, workspace_id: str, project_id: str, case_id: str, actor: str = "author@qualiforge.local") -> dict:
    response = client.post(
        f"/api/workspaces/{workspace_id}/projects/{project_id}/test-cases/{case_id}/submit-review?actor_email={actor}"
    )
    assert response.status_code == 200, response.text
    return response.json()


def review_case(
    client: TestClient,
    workspace_id: str,
    project_id: str,
    case_id: str,
    action: str,
    actor: str = "owner@qualiforge.local",
    **extra,
) -> dict:
    payload = {"action": action, "comment": extra.pop("comment", f"{action} comment"), **extra}
    response = client.post(
        f"/api/workspaces/{workspace_id}/projects/{project_id}/test-cases/{case_id}/reviews?actor_email={actor}",
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_case_review_flow_blocks_self_review_and_creates_approval_revision() -> None:
    client = make_client()
    workspace = create_workspace(client)
    add_member(client, workspace["id"])
    project = create_project(client, workspace["id"])
    test_case = create_case(client, workspace["id"], project["id"])

    assert test_case["status"] == "draft"
    submitted = submit_case(client, workspace["id"], project["id"], test_case["id"])
    assert submitted["status"] == "pending_review"
    assert submitted["submitted_by"] == "author@qualiforge.local"

    forbidden = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/test-cases/{test_case['id']}/reviews?actor_email=author@qualiforge.local",
        json={"action": "approved", "comment": "self approve"},
    )
    assert forbidden.status_code == 403

    approved_review = review_case(client, workspace["id"], project["id"], test_case["id"], "approved", comment="Looks good")
    assert approved_review["action"] == "approved"
    assert approved_review["revision_id"] is not None

    approved_case = client.get(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/test-cases/{test_case['id']}"
    ).json()
    assert approved_case["status"] == "approved"
    assert approved_case["approved_by"] == "owner@qualiforge.local"
    assert approved_case["current_revision_number"] == 1

    revisions = client.get(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/test-cases/{test_case['id']}/revisions"
    ).json()
    assert len(revisions) == 1
    assert revisions[0]["revision_number"] == 1
    assert revisions[0]["content_snapshot"]["title"] == "Checkout payment succeeds"


def test_reviews_support_comment_edit_request_changes_and_reject() -> None:
    client = make_client()
    workspace = create_workspace(client)
    add_member(client, workspace["id"])
    project = create_project(client, workspace["id"])
    test_case = create_case(client, workspace["id"], project["id"])
    submit_case(client, workspace["id"], project["id"], test_case["id"])

    comment = review_case(client, workspace["id"], project["id"], test_case["id"], "commented", comment="Need clearer expected result")
    assert comment["action"] == "commented"

    edited = review_case(
        client,
        workspace["id"],
        project["id"],
        test_case["id"],
        "edited",
        comment="Clarified expected result",
        edits={"expected_result": "Payment status is paid and receipt is visible"},
    )
    assert edited["action"] == "edited"
    updated_case = client.get(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/test-cases/{test_case['id']}"
    ).json()
    assert updated_case["expected_result"] == "Payment status is paid and receipt is visible"

    changes = review_case(client, workspace["id"], project["id"], test_case["id"], "changes_requested")
    assert changes["action"] == "changes_requested"
    assert client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/test-cases/{test_case['id']}").json()["status"] == "draft"

    submit_case(client, workspace["id"], project["id"], test_case["id"])
    rejected = review_case(client, workspace["id"], project["id"], test_case["id"], "rejected", comment="Duplicate")
    assert rejected["action"] == "rejected"
    assert client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/test-cases/{test_case['id']}").json()["status"] == "rejected"

    reviews = client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/test-cases/{test_case['id']}/reviews").json()
    assert {"commented", "edited", "changes_requested", "rejected"} <= {review["action"] for review in reviews}


def test_workspace_owner_can_allow_self_review_and_configure_update_review_policy() -> None:
    client = make_client()
    workspace = create_workspace(client)
    project = create_project(client, workspace["id"])
    owner_case = create_case(client, workspace["id"], project["id"], actor="owner@qualiforge.local")
    submit_case(client, workspace["id"], project["id"], owner_case["id"], actor="owner@qualiforge.local")

    default_self_review = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/test-cases/{owner_case['id']}/reviews?actor_email=owner@qualiforge.local",
        json={"action": "approved", "comment": "self approve"},
    )
    assert default_self_review.status_code == 403

    settings = client.put(
        f"/api/workspaces/{workspace['id']}/review-settings?actor_email=owner@qualiforge.local",
        json={"allow_self_review": True, "require_review_on_case_update": True},
    )
    assert settings.status_code == 200
    assert settings.json()["allow_self_review"] is True

    review_case(client, workspace["id"], project["id"], owner_case["id"], "approved", actor="owner@qualiforge.local")
    approved_case = client.get(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/test-cases/{owner_case['id']}"
    ).json()
    assert approved_case["status"] == "approved"

    updated = client.patch(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/test-cases/{owner_case['id']}?actor_email=owner@qualiforge.local",
        json={"title": "Checkout payment succeeds after 3DS"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "pending_review"
    assert updated.json()["current_revision_number"] == 2

    review_case(client, workspace["id"], project["id"], owner_case["id"], "approved", actor="owner@qualiforge.local")
    client.put(
        f"/api/workspaces/{workspace['id']}/review-settings?actor_email=owner@qualiforge.local",
        json={"allow_self_review": True, "require_review_on_case_update": False},
    )
    no_review_update = client.patch(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/test-cases/{owner_case['id']}?actor_email=owner@qualiforge.local",
        json={"risk": "medium"},
    )
    assert no_review_update.status_code == 200
    assert no_review_update.json()["status"] == "approved"
    assert no_review_update.json()["current_revision_number"] == 4

    revisions = client.get(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/test-cases/{owner_case['id']}/revisions"
    ).json()
    assert [revision["revision_number"] for revision in revisions] == [4, 3, 2, 1]
