from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_endpoint_reports_backend_ok() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "backend"


def test_dashboard_summary_contains_issue_one() -> None:
    response = client.get("/api/dashboard/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mvp_stage"] == "基础平台、Workspace、AI 配置、Git Sandbox、Module Mapping、历史用例导入、用例评审治理、Diff 决策分析与 AI 测试建议"
    assert payload["work_items"][0]["issue"] == "#1"
    assert payload["work_items"][2]["issue"] == "#3"
    assert payload["work_items"][6]["issue"] == "#7"
    assert payload["work_items"][7]["issue"] == "#8"
    assert payload["work_items"][8]["issue"] == "#9"


def test_local_login_accepts_private_deployment_email() -> None:
    response = client.post(
        "/api/auth/login",
        json={
            "email": "owner@qualiforge.local",
            "display_name": "Workspace Owner",
            "workspace_name": "QualiForge Lab",
        },
    )

    assert response.status_code == 200
    assert response.json()["user"]["role"] == "WorkspaceOwner"
