from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.git.models import WorkspaceGitLabCredential
from app.git.sandbox import git_auth_env, git_command_for_log
from app.gitlab import ensure_safe_sandbox_path
from app.main import create_app


def make_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        redis_url="redis://localhost:6379/15",
        git_sandbox_root=str(tmp_path / "sandbox"),
        git_sync_timeout_seconds=30,
        git_repo_size_limit_mb=128,
        git_diff_file_limit=250,
    )
    return TestClient(create_app(settings))


def create_workspace(client: TestClient) -> dict:
    response = client.post(
        "/api/workspaces",
        json={
            "name": "Git Lab",
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


def create_source_repo(tmp_path: Path) -> Path:
    if shutil.which("git") is None:
        pytest.skip("git executable is not available")
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init"], cwd=source, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=source, check=True)
    (source / "README.md").write_text("# fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=source, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=source, check=True, capture_output=True, text=True)
    return source


def test_gitlab_token_can_be_saved_by_owner_but_never_returned_plaintext(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    workspace = create_workspace(client)
    add_member(client, workspace["id"])

    forbidden = client.put(
        f"/api/workspaces/{workspace['id']}/gitlab-token?actor_email=member@qualiforge.local",
        json={"gitlab_base_url": "https://gitlab.example.com", "token": "glpat-member-secret"},
    )
    assert forbidden.status_code == 403

    saved = client.put(
        f"/api/workspaces/{workspace['id']}/gitlab-token?actor_email=owner@qualiforge.local",
        json={"gitlab_base_url": "https://gitlab.example.com", "token": "glpat-owner-secret"},
    )
    assert saved.status_code == 200
    payload = saved.json()
    assert payload["token_masked"] == "glpa...cret"
    assert payload["has_token"] is True
    assert "token" not in payload

    fetched = client.get(f"/api/workspaces/{workspace['id']}/gitlab-token").json()
    assert fetched["token_masked"] == "glpa...cret"
    assert "glpat-owner-secret" not in str(fetched)
    audit_logs = client.get(f"/api/workspaces/{workspace['id']}/audit-logs?actor_email=owner@qualiforge.local").json()
    assert "glpat-owner-secret" not in str(audit_logs)


def test_git_auth_env_uses_basic_auth_for_git_over_https_and_scopes_to_gitlab_base_url() -> None:
    credential = WorkspaceGitLabCredential(
        workspace_id="workspace",
        gitlab_base_url="https://gitlab.example.com",
        token_secret="glpat-owner-secret",
        updated_by="owner@qualiforge.local",
    )

    auth_env = git_auth_env(credential, "https://gitlab.example.com/team/checkout-api.git")

    assert auth_env["GIT_CONFIG_COUNT"] == "1"
    assert auth_env["GIT_CONFIG_KEY_0"] == "http.extraHeader"
    assert auth_env["GIT_CONFIG_VALUE_0"] == "Authorization: Basic b2F1dGgyOmdscGF0LW93bmVyLXNlY3JldA=="
    assert "glpat-owner-secret" not in str(auth_env)
    assert git_auth_env(credential, "https://gitlab.example.com.evil/team/checkout-api.git") == {}


def test_git_command_for_log_redacts_auth_headers() -> None:
    logged = git_command_for_log(["git", "-c", "http.extraHeader=Authorization: Basic secret", "clone"])

    assert logged == "git -c <redacted-git-header> clone"


def test_existing_mirror_sync_fetches_with_basic_auth_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = make_client(tmp_path)
    workspace = create_workspace(client)
    project = create_project(client, workspace["id"])
    saved = client.put(
        f"/api/workspaces/{workspace['id']}/gitlab-token?actor_email=owner@qualiforge.local",
        json={"gitlab_base_url": "https://gitlab.example.com", "token": "glpat-owner-secret"},
    )
    assert saved.status_code == 200
    repository_response = client.post(
        f"/api/workspaces/{workspace['id']}/repositories?actor_email=owner@qualiforge.local",
        json={
            "project_id": project["id"],
            "name": "Checkout API",
            "remote_url": "https://gitlab.example.com/team/checkout-api.git",
            "default_branch": "main",
        },
    )
    assert repository_response.status_code == 201
    repository = repository_response.json()
    Path(repository["mirror_path"]).mkdir(parents=True)
    calls: list[tuple[list[str], dict[str, str] | None]] = []

    def fake_run_git(
        command: list[str],
        timeout_seconds: int,
        key_logs: list[str],
        env_overrides: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        calls.append((command, env_overrides))
        key_logs.append("$ " + " ".join(command))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("app.git.sandbox.run_git", fake_run_git)

    queued = client.post(
        f"/api/workspaces/{workspace['id']}/repositories/{repository['id']}/sync?actor_email=owner@qualiforge.local"
    )

    assert queued.status_code == 202
    assert calls[0] == (
        ["git", "-C", repository["mirror_path"], "remote", "set-url", "origin", "https://gitlab.example.com/team/checkout-api.git"],
        None,
    )
    assert calls[1][0] == ["git", "-C", repository["mirror_path"], "remote", "update", "--prune"]
    assert calls[1][1] == {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.extraHeader",
        "GIT_CONFIG_VALUE_0": "Authorization: Basic b2F1dGgyOmdscGF0LW93bmVyLXNlY3JldA==",
    }
    jobs = client.get(f"/api/workspaces/{workspace['id']}/jobs?repository_id={repository['id']}").json()
    assert jobs[0]["status"] == "succeeded", jobs[0]
    assert "glpat-owner-secret" not in str(jobs[0]["key_logs"])


def test_project_can_bind_multiple_repositories_with_system_generated_sandbox_paths(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    workspace = create_workspace(client)
    project = create_project(client, workspace["id"])

    first = client.post(
        f"/api/workspaces/{workspace['id']}/repositories?actor_email=owner@qualiforge.local",
        json={
            "project_id": project["id"],
            "name": "Checkout API",
            "remote_url": "https://gitlab.example.com/team/checkout-api.git",
            "default_branch": "main",
        },
    )
    second = client.post(
        f"/api/workspaces/{workspace['id']}/repositories?actor_email=owner@qualiforge.local",
        json={
            "project_id": project["id"],
            "name": "Checkout Web",
            "remote_url": "https://gitlab.example.com/team/checkout-web.git",
            "default_branch": "main",
            "repo_size_limit_mb": 512,
            "diff_file_limit": 300,
            "sync_timeout_seconds": 60,
        },
    )

    assert first.status_code == 201
    assert second.status_code == 201
    repositories = client.get(f"/api/workspaces/{workspace['id']}/repositories?project_id={project['id']}").json()
    assert len(repositories) == 2
    for repository in repositories:
        mirror_path = Path(repository["mirror_path"]).resolve(strict=False)
        sandbox_root = (tmp_path / "sandbox").resolve(strict=False)
        assert sandbox_root == mirror_path or sandbox_root in mirror_path.parents
        assert workspace["id"][:12] in mirror_path.parts
        assert project["id"][:12] in mirror_path.parts
    assert {repository["diff_file_limit"] for repository in repositories} == {250, 300}


def test_repository_sync_runs_job_and_records_status_logs_and_mirror(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    workspace = create_workspace(client)
    project = create_project(client, workspace["id"])
    source = create_source_repo(tmp_path)

    repository_response = client.post(
        f"/api/workspaces/{workspace['id']}/repositories?actor_email=owner@qualiforge.local",
        json={
            "project_id": project["id"],
            "name": "Local Fixture",
            "remote_url": source.as_uri(),
            "default_branch": "master",
            "repo_size_limit_mb": 128,
            "diff_file_limit": 250,
            "sync_timeout_seconds": 30,
        },
    )
    assert repository_response.status_code == 201
    repository = repository_response.json()

    queued = client.post(
        f"/api/workspaces/{workspace['id']}/repositories/{repository['id']}/sync?actor_email=owner@qualiforge.local"
    )
    assert queued.status_code == 202

    jobs = client.get(f"/api/workspaces/{workspace['id']}/jobs?repository_id={repository['id']}").json()
    assert jobs[0]["status"] == "succeeded", jobs[0]
    assert jobs[0]["error_summary"] == ""
    assert any("git clone --mirror" in entry for entry in jobs[0]["key_logs"])
    assert Path(repository["mirror_path"]).exists()

    repositories = client.get(f"/api/workspaces/{workspace['id']}/repositories?project_id={project['id']}").json()
    assert repositories[0]["status"] == "synced"
    assert repositories[0]["last_synced_at"] is not None


def test_repository_sync_records_failure_for_invalid_remote(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    workspace = create_workspace(client)
    project = create_project(client, workspace["id"])

    repository = client.post(
        f"/api/workspaces/{workspace['id']}/repositories?actor_email=owner@qualiforge.local",
        json={
            "project_id": project["id"],
            "name": "Missing Repo",
            "remote_url": (tmp_path / "missing").as_uri(),
            "default_branch": "main",
            "sync_timeout_seconds": 5,
        },
    ).json()
    client.post(f"/api/workspaces/{workspace['id']}/repositories/{repository['id']}/sync?actor_email=owner@qualiforge.local")

    jobs = client.get(f"/api/workspaces/{workspace['id']}/jobs?repository_id={repository['id']}").json()
    assert jobs[0]["status"] == "failed"
    assert jobs[0]["error_summary"] != ""
    repositories = client.get(f"/api/workspaces/{workspace['id']}/repositories?project_id={project['id']}").json()
    assert repositories[0]["status"] == "sync_failed"


def test_sandbox_path_rejects_symlink_escape_when_supported(tmp_path: Path) -> None:
    root = tmp_path / "sandbox"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    symlink = root / "workspace"
    try:
        symlink.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("filesystem does not allow directory symlink creation")

    with pytest.raises(ValueError, match="symlink|escapes"):
        ensure_safe_sandbox_path(root, symlink / "project" / "repo.git")
