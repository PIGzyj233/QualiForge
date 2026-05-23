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


def create_module(client: TestClient, workspace_id: str, project_id: str, name: str = "支付") -> dict:
    response = client.post(
        f"/api/workspaces/{workspace_id}/projects/{project_id}/modules?actor_email=owner@qualiforge.local",
        json={"name": name, "code": "PAYMENT", "description": "Payment domain", "owner": "QA"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_case(
    client: TestClient,
    workspace_id: str,
    project_id: str,
    module_id: str,
    actor: str = "author@qualiforge.local",
) -> dict:
    response = client.post(
        f"/api/workspaces/{workspace_id}/projects/{project_id}/test-cases?actor_email={actor}",
        json={
            "module_id": module_id,
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
    comment: str = "review comment",
) -> dict:
    response = client.post(
        f"/api/workspaces/{workspace_id}/projects/{project_id}/test-cases/{case_id}/reviews?actor_email={actor}",
        json={"action": action, "comment": comment},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_manual_create_submit_approve_creates_revision_and_blocks_self_review() -> None:
    client = make_client()
    workspace = create_workspace(client)
    add_member(client, workspace["id"])
    project = create_project(client, workspace["id"])
    module = create_module(client, workspace["id"], project["id"])
    test_case = create_case(client, workspace["id"], project["id"], module["id"])

    assert test_case["lifecycle_status"] == "draft"
    assert test_case["active_draft"]["source_type"] == "manual"
    submitted = submit_case(client, workspace["id"], project["id"], test_case["id"])
    assert submitted["review_status"] == "pending_review"
    assert submitted["open_cycle"]["submitted_by"] == "author@qualiforge.local"

    forbidden = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/test-cases/{test_case['id']}/reviews?actor_email=author@qualiforge.local",
        json={"action": "approved", "comment": "self approve"},
    )
    assert forbidden.status_code == 403

    approved = review_case(client, workspace["id"], project["id"], test_case["id"], "approved", comment="Looks good")
    assert approved["action"] == "approved"
    assert approved["revision_id"] is not None

    approved_case = client.get(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/test-cases/{test_case['id']}"
    ).json()
    assert approved_case["lifecycle_status"] == "active"
    assert approved_case["current_revision_number"] == 1
    assert approved_case["active_draft"] is None
    assert approved_case["current_revision"]["content_snapshot"]["title"] == "Checkout payment succeeds"


def test_changes_requested_requires_comment_and_addressing_returns_to_queue_then_rejects() -> None:
    client = make_client()
    workspace = create_workspace(client)
    add_member(client, workspace["id"])
    project = create_project(client, workspace["id"])
    module = create_module(client, workspace["id"], project["id"])
    test_case = create_case(client, workspace["id"], project["id"], module["id"])
    submitted = submit_case(client, workspace["id"], project["id"], test_case["id"])
    cycle_id = submitted["open_cycle"]["id"]

    empty_comment = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/review-cycles/{cycle_id}/request-changes?actor_email=owner@qualiforge.local",
        json={"comment": ""},
    )
    assert empty_comment.status_code == 422

    changes = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/review-cycles/{cycle_id}/request-changes?actor_email=owner@qualiforge.local",
        json={"comment": "Expected result needs receipt check"},
    )
    assert changes.status_code == 201
    assert changes.json()["action"] == "changes_requested"
    assert client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/review-cycles").json() == []

    detail = client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/test-cases/{test_case['id']}").json()
    draft_id = detail["active_draft"]["id"]
    updated = client.patch(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/case-drafts/{draft_id}?actor_email=author@qualiforge.local",
        json={"expected_result": "Order is paid and receipt is visible"},
    )
    assert updated.status_code == 200

    addressed = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/review-cycles/{cycle_id}/address-changes?actor_email=author@qualiforge.local",
        json={"comment": "Added receipt expectation", "diff_summary": {"expected_result": "updated"}},
    )
    assert addressed.status_code == 201
    assert addressed.json()["action"] == "changes_addressed"
    queue = client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/review-cycles").json()
    assert [item["id"] for item in queue] == [test_case["id"]]

    rejected = review_case(client, workspace["id"], project["id"], test_case["id"], "rejected", comment="Duplicate")
    assert rejected["action"] == "rejected"
    rejected_case = client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/test-cases/{test_case['id']}").json()
    assert rejected_case["lifecycle_status"] == "draft"
    assert rejected_case["active_draft"] is None


def test_active_edit_draft_does_not_overwrite_current_revision_until_approved() -> None:
    client = make_client()
    workspace = create_workspace(client)
    project = create_project(client, workspace["id"])
    module = create_module(client, workspace["id"], project["id"])
    client.put(
        f"/api/workspaces/{workspace['id']}/review-settings?actor_email=owner@qualiforge.local",
        json={"allow_self_review": True, "require_review_on_case_update": True},
    )
    owner_case = create_case(client, workspace["id"], project["id"], module["id"], actor="owner@qualiforge.local")
    submit_case(client, workspace["id"], project["id"], owner_case["id"], actor="owner@qualiforge.local")
    review_case(client, workspace["id"], project["id"], owner_case["id"], "approved", actor="owner@qualiforge.local")

    edit_draft = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/test-cases/{owner_case['id']}/drafts?actor_email=owner@qualiforge.local"
    )
    assert edit_draft.status_code == 201
    draft_id = edit_draft.json()["id"]
    patched = client.patch(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/case-drafts/{draft_id}?actor_email=owner@qualiforge.local",
        json={"title": "Checkout payment succeeds after 3DS"},
    )
    assert patched.status_code == 200

    before_approval = client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/test-cases/{owner_case['id']}").json()
    assert before_approval["title"] == "Checkout payment succeeds after 3DS"
    assert before_approval["current_revision"]["content_snapshot"]["title"] == "Checkout payment succeeds"
    assert before_approval["current_revision_number"] == 1

    submit_case(client, workspace["id"], project["id"], owner_case["id"], actor="owner@qualiforge.local")
    review_case(client, workspace["id"], project["id"], owner_case["id"], "approved", actor="owner@qualiforge.local", comment="v2")
    after_approval = client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/test-cases/{owner_case['id']}").json()
    assert after_approval["current_revision_number"] == 2
    assert after_approval["current_revision"]["content_snapshot"]["title"] == "Checkout payment succeeds after 3DS"

    revisions = client.get(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/test-cases/{owner_case['id']}/revisions"
    ).json()
    assert [revision["revision_number"] for revision in revisions] == [2, 1]
