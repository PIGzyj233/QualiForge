from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.platform.config import Settings
from app.main import create_app


OWNER = "owner@qualiforge.local"


def make_client(
    tmp_path: Path,
    model_gateway_transport: Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]] | None = None,
    settings_overrides: dict[str, Any] | None = None,
) -> TestClient:
    settings_values: dict[str, Any] = {
        "database_url": "sqlite+pysqlite:///:memory:",
        "redis_url": "redis://localhost:6379/15",
        "git_sandbox_root": str(tmp_path / "sandbox"),
        "git_sync_timeout_seconds": 30,
        "git_repo_size_limit_mb": 128,
        "git_diff_file_limit": 250,
        "model_gateway_api_base_url": "",
        "model_gateway_api_key": "",
        "model_gateway_default_model": "deepseek-v4-pro",
    }
    settings_values.update(settings_overrides or {})
    app = create_app(Settings(**settings_values))
    if model_gateway_transport is not None:
        app.state.model_gateway_transport = model_gateway_transport
    return TestClient(app)


def create_workspace_project(client: TestClient) -> tuple[dict, dict]:
    workspace = client.post(
        "/api/workspaces",
        json={
            "name": "Diff Lab",
            "owner_email": OWNER,
            "owner_display_name": "Workspace Owner",
        },
    ).json()
    project = client.post(
        f"/api/workspaces/{workspace['id']}/projects?actor_email={OWNER}",
        json={"name": "Checkout", "key": "CHECKOUT", "description": "Checkout service"},
    ).json()
    return workspace, project


def create_module_with_rules(client: TestClient, workspace_id: str, project_id: str) -> dict:
    module = client.post(
        f"/api/workspaces/{workspace_id}/projects/{project_id}/modules?actor_email={OWNER}",
        json={"key": "PAYMENT", "name": "Payment", "description": "Payment flows", "owner": "QA"},
    ).json()
    examples = [
        ("directory", "src/payment", 95),
        ("api", "/checkout", 90),
        ("config_key", "payment_timeout", 88),
        ("database_migration", "migrations", 92),
    ]
    for rule_type, pattern, confidence in examples:
        response = client.post(
            f"/api/workspaces/{workspace_id}/projects/{project_id}/modules/{module['id']}/mapping-rules?actor_email={OWNER}",
            json={
                "rule_type": rule_type,
                "pattern": pattern,
                "source": "manual",
                "description": f"{rule_type} signal",
                "confidence": confidence,
            },
        )
        assert response.status_code == 201
    return module


def git_run(repo: Path, args: list[str]) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def create_diff_fixture_repo(tmp_path: Path) -> Path:
    if shutil.which("git") is None:
        pytest.skip("git executable is not available")

    source = tmp_path / "source"
    (source / "src" / "payment").mkdir(parents=True)
    (source / "config").mkdir()
    git_run(tmp_path, ["init", str(source)])
    git_run(source, ["config", "user.email", "tester@example.com"])
    git_run(source, ["config", "user.name", "Tester"])

    (source / "src" / "payment" / "checkout.py").write_text(
        "\n".join(
            [
                "from fastapi import APIRouter",
                "",
                "router = APIRouter()",
                "",
                "@router.post('/checkout/pay')",
                "def pay_order():",
                "    return {'status': 'paid'}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (source / "config" / "payment.yaml").write_text("payment_timeout: 15\n", encoding="utf-8")
    git_run(source, ["add", "."])
    git_run(source, ["commit", "-m", "base checkout"])
    git_run(source, ["tag", "v1"])

    (source / "src" / "payment" / "checkout.py").write_text(
        "\n".join(
            [
                "from fastapi import APIRouter",
                "",
                "router = APIRouter()",
                "",
                "@router.post('/checkout/pay')",
                "def pay_order():",
                "    return {'status': 'paid'}",
                "",
                "@router.post('/checkout/refund')",
                "def refund_order():",
                "    return {'status': 'refunded'}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (source / "config" / "payment.yaml").write_text("payment_timeout: 30\nrefund_enabled: true\n", encoding="utf-8")
    (source / "migrations").mkdir()
    (source / "migrations" / "002_add_refunds.sql").write_text(
        "create table refunds (id integer primary key, order_id integer not null);\n",
        encoding="utf-8",
    )
    (source / "tests").mkdir()
    (source / "tests" / "test_checkout.py").write_text("def test_refund_order():\n    assert True\n", encoding="utf-8")
    git_run(source, ["add", "."])
    git_run(source, ["commit", "-m", "target refund"])
    git_run(source, ["tag", "v2"])
    return source


def bind_and_sync_repository(client: TestClient, workspace_id: str, project_id: str, source: Path) -> dict:
    repository_response = client.post(
        f"/api/workspaces/{workspace_id}/repositories?actor_email={OWNER}",
        json={
            "project_id": project_id,
            "name": "Checkout Fixture",
            "remote_url": source.as_uri(),
            "default_branch": "master",
            "repo_size_limit_mb": 128,
            "diff_file_limit": 250,
            "sync_timeout_seconds": 30,
        },
    )
    assert repository_response.status_code == 201
    repository = repository_response.json()
    sync_response = client.post(f"/api/workspaces/{workspace_id}/repositories/{repository['id']}/sync?actor_email={OWNER}")
    assert sync_response.status_code == 202
    synced = client.get(f"/api/workspaces/{workspace_id}/repositories?project_id={project_id}").json()[0]
    assert synced["status"] == "synced"
    return synced


def test_diff_analysis_creates_job_and_testing_decision_view(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    workspace, project = create_workspace_project(client)
    module = create_module_with_rules(client, workspace["id"], project["id"])
    source = create_diff_fixture_repo(tmp_path)
    repository = bind_and_sync_repository(client, workspace["id"], project["id"], source)

    response = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/diff-analyses?actor_email={OWNER}",
        json={"repository_id": repository["id"], "base_ref": "v1", "target_ref": "v2"},
    )

    assert response.status_code == 201
    analysis = response.json()
    assert analysis["status"] == "succeeded", analysis
    assert analysis["risk_level"] == "high"
    assert analysis["job_id"]
    assert "overall risk high" in analysis["summary"]
    assert any("Temporary worktree" in entry for entry in analysis["key_logs"])

    by_path = {item["path"]: item for item in analysis["file_changes"]}
    assert by_path["src/payment/checkout.py"]["module_id"] == module["id"]
    assert by_path["src/payment/checkout.py"]["module_key"] == "PAYMENT"
    checkout_structures = {item["type"] for item in by_path["src/payment/checkout.py"]["structure_changes"]}
    assert {"function", "api_route"} <= checkout_structures
    checkout_hunks = by_path["src/payment/checkout.py"]["diff_hunks"]
    assert checkout_hunks
    assert any("+@router.post('/checkout/refund')" in line for hunk in checkout_hunks for line in hunk["lines"])
    assert by_path["migrations/002_add_refunds.sql"]["is_migration"] is True
    assert by_path["migrations/002_add_refunds.sql"]["risk_level"] == "high"
    assert by_path["tests/test_checkout.py"]["is_test_file"] is True

    payment_impact = next(item for item in analysis["module_impacts"] if item["module_key"] == "PAYMENT")
    assert payment_impact["risk_level"] == "high"
    assert payment_impact["confidence"] >= 90
    assert payment_impact["recommended_tests"]
    assert any("Run full regression for PAYMENT" == item for item in analysis["recommended_scope"])

    listed = client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/diff-analyses").json()
    assert listed[0]["id"] == analysis["id"]
    fetched = client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/diff-analyses/{analysis['id']}").json()
    assert fetched["file_changes"] == analysis["file_changes"]

    jobs = client.get(f"/api/workspaces/{workspace['id']}/jobs?repository_id={repository['id']}").json()
    assert jobs[0]["job_type"] == "diff_analysis"
    assert jobs[0]["status"] == "succeeded"


def test_diff_analysis_fetches_new_tags_before_resolving_refs(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    workspace, project = create_workspace_project(client)
    create_module_with_rules(client, workspace["id"], project["id"])
    source = create_diff_fixture_repo(tmp_path)
    repository = bind_and_sync_repository(client, workspace["id"], project["id"], source)

    (source / "src" / "payment" / "checkout.py").write_text(
        "\n".join(
            [
                "from fastapi import APIRouter",
                "",
                "router = APIRouter()",
                "",
                "@router.post('/checkout/pay')",
                "def pay_order():",
                "    return {'status': 'paid'}",
                "",
                "@router.post('/checkout/refund')",
                "def refund_order():",
                "    return {'status': 'refunded'}",
                "",
                "@router.post('/checkout/void')",
                "def void_order():",
                "    return {'status': 'voided'}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    git_run(source, ["add", "."])
    git_run(source, ["commit", "-m", "target void"])
    git_run(source, ["tag", "v3"])

    response = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/diff-analyses?actor_email={OWNER}",
        json={"repository_id": repository["id"], "base_ref": "v2", "target_ref": "v3"},
    )

    assert response.status_code == 201
    analysis = response.json()
    assert analysis["status"] == "succeeded", analysis
    assert any("fetch --prune --tags --force origin" in entry for entry in analysis["key_logs"])
    assert any("+@router.post('/checkout/void')" in line for item in analysis["file_changes"] for hunk in item["diff_hunks"] for line in hunk["lines"])


def test_diff_analysis_reports_missing_refs_after_refresh_with_logs(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    workspace, project = create_workspace_project(client)
    source = create_diff_fixture_repo(tmp_path)
    repository = bind_and_sync_repository(client, workspace["id"], project["id"], source)

    response = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/diff-analyses?actor_email={OWNER}",
        json={"repository_id": repository["id"], "base_ref": "missing-base", "target_ref": "missing-target"},
    )

    assert response.status_code == 201
    analysis = response.json()
    assert analysis["status"] == "failed", analysis
    assert "after refreshing repository refs" in analysis["error_summary"]
    assert "base ref missing-base" in analysis["error_summary"]
    assert "target ref missing-target" in analysis["error_summary"]
    assert any("fetch --prune --tags --force origin" in entry for entry in analysis["key_logs"])
    assert any("rev-parse --verify missing-base^{commit}" in entry for entry in analysis["key_logs"])
    assert any("rev-parse --verify missing-target^{commit}" in entry for entry in analysis["key_logs"])


def test_diff_analysis_requires_synced_repository(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    workspace, project = create_workspace_project(client)
    source = create_diff_fixture_repo(tmp_path)
    repository = client.post(
        f"/api/workspaces/{workspace['id']}/repositories?actor_email={OWNER}",
        json={
            "project_id": project["id"],
            "name": "Unsynced Fixture",
            "remote_url": source.as_uri(),
            "default_branch": "master",
        },
    ).json()

    response = client.post(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/diff-analyses?actor_email={OWNER}",
        json={"repository_id": repository["id"], "base_ref": "v1", "target_ref": "v2"},
    )

    assert response.status_code == 409
    assert "synced" in response.json()["detail"]
