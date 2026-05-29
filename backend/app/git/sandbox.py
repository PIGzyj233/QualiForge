from __future__ import annotations

import base64
import os
import shutil
import subprocess
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.git.models import (
    GitRepository,
    GitLabCredentialResponse,
    Job,
    JobResponse,
    JobStatus,
    RepositoryResponse,
    RepositoryStatus,
    WorkspaceGitLabCredential,
)
from app.platform.config import Settings
from app.platform.database import Database
from app.workspace.routes import now_utc


def mask_token(token: str) -> str:
    if len(token) <= 8:
        return "****"
    return f"{token[:4]}...{token[-4:]}"


def credential_to_response(credential: WorkspaceGitLabCredential) -> GitLabCredentialResponse:
    return GitLabCredentialResponse(
        id=credential.id,
        workspace_id=credential.workspace_id,
        gitlab_base_url=credential.gitlab_base_url,
        token_masked=mask_token(credential.token_secret),
        has_token=bool(credential.token_secret),
        updated_by=credential.updated_by,
        created_at=credential.created_at,
        updated_at=credential.updated_at,
    )


def repository_to_response(repository: GitRepository) -> RepositoryResponse:
    return RepositoryResponse(
        id=repository.id,
        workspace_id=repository.workspace_id,
        project_id=repository.project_id,
        name=repository.name,
        remote_url=repository.remote_url,
        default_branch=repository.default_branch,
        mirror_path=repository.mirror_path,
        status=repository.status,
        last_synced_at=repository.last_synced_at,
        repo_size_limit_mb=repository.repo_size_limit_mb,
        diff_file_limit=repository.diff_file_limit,
        sync_timeout_seconds=repository.sync_timeout_seconds,
        created_at=repository.created_at,
        updated_at=repository.updated_at,
    )


def job_to_response(job: Job) -> JobResponse:
    return JobResponse(
        id=job.id,
        workspace_id=job.workspace_id,
        project_id=job.project_id,
        repository_id=job.repository_id,
        job_type=job.job_type,
        status=job.status,
        created_by=job.created_by,
        input_summary=job.input_summary,
        output_summary=job.output_summary,
        error_summary=job.error_summary,
        key_logs=job.key_logs,
        timeout_seconds=job.timeout_seconds,
        repo_size_limit_mb=job.repo_size_limit_mb,
        diff_file_limit=job.diff_file_limit,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def sandbox_path(settings: Settings, workspace_id: str, project_id: str, repository_id: str) -> Path:
    root = Path(settings.git_sandbox_root).expanduser()
    return root / workspace_id[:12] / project_id[:12] / repository_id[:12]


def ensure_safe_sandbox_path(root: Path, target: Path) -> Path:
    root_resolved = root.expanduser().resolve(strict=False)
    target_resolved = target.expanduser().resolve(strict=False)
    if root_resolved != target_resolved and root_resolved not in target_resolved.parents:
        raise ValueError("Sandbox path escapes configured root")

    current = root_resolved
    relative_parts = target_resolved.relative_to(root_resolved).parts
    for part in relative_parts[:-1]:
        current = current / part
        if current.exists() and current.is_symlink():
            raise ValueError("Sandbox path contains a symlink")
    if target_resolved.exists() and target_resolved.is_symlink():
        raise ValueError("Repository mirror path is a symlink")
    return target_resolved


def remove_tree_readonly(path: Path) -> None:
    def retry_with_write_permission(function, target, exc_info) -> None:
        try:
            Path(target).chmod(0o700)
            function(target)
        except Exception:
            raise exc_info[1]

    shutil.rmtree(path, onexc=retry_with_write_permission)


def directory_size_mb(path: Path) -> float:
    total = 0
    for item in path.rglob("*"):
        if item.is_file() and not item.is_symlink():
            total += item.stat().st_size
    return total / 1024 / 1024


def is_full_checkout(path: Path) -> bool:
    return (path / ".git").exists()


def checkout_default_branch(
    repository_path: Path,
    default_branch: str,
    timeout_seconds: int,
    key_logs: list[str],
) -> None:
    checkout = run_git(
        ["git", "-C", str(repository_path), "checkout", "-B", default_branch, f"origin/{default_branch}"],
        timeout_seconds,
        key_logs,
    )
    if checkout.returncode == 0:
        reset = run_git(
            ["git", "-C", str(repository_path), "reset", "--hard", f"origin/{default_branch}"],
            timeout_seconds,
            key_logs,
        )
        if reset.returncode != 0:
            stderr = reset.stderr.strip()[:500] or f"git exited with {reset.returncode}"
            raise RuntimeError(stderr)
        return

    fallback = run_git(["git", "-C", str(repository_path), "checkout", default_branch], timeout_seconds, key_logs)
    if fallback.returncode != 0:
        stderr = (fallback.stderr or checkout.stderr).strip()[:500] or f"git exited with {fallback.returncode}"
        raise RuntimeError(stderr)


def get_repository_or_404(db: Session, workspace_id: str, repository_id: str) -> GitRepository:
    repository = db.scalar(
        select(GitRepository).where(
            GitRepository.id == repository_id,
            GitRepository.workspace_id == workspace_id,
        )
    )
    if repository is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    return repository


def get_gitlab_credential(db: Session, workspace_id: str) -> WorkspaceGitLabCredential | None:
    return db.scalar(select(WorkspaceGitLabCredential).where(WorkspaceGitLabCredential.workspace_id == workspace_id))


def git_command_for_log(command: list[str]) -> str:
    sensitive_markers = ("PRIVATE-TOKEN:", "Authorization:")
    return " ".join("<redacted-git-header>" if any(marker in part for marker in sensitive_markers) else part for part in command)


def git_auth_env(credential: WorkspaceGitLabCredential | None, remote_url: str) -> dict[str, str]:
    if credential is None or not remote_url.startswith(("http://", "https://")):
        return {}

    gitlab_base_url = credential.gitlab_base_url.rstrip("/")
    if remote_url != gitlab_base_url and not remote_url.startswith(f"{gitlab_base_url}/"):
        return {}

    auth_value = base64.b64encode(f"oauth2:{credential.token_secret}".encode("utf-8")).decode("ascii")
    return {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.extraHeader",
        "GIT_CONFIG_VALUE_0": f"Authorization: Basic {auth_value}",
    }


def run_git(
    command: list[str],
    timeout_seconds: int,
    key_logs: list[str],
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    key_logs.append(f"$ {git_command_for_log(command)}")
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        command,
        capture_output=True,
        check=False,
        env=env,
        text=True,
        timeout=timeout_seconds,
    )


def refresh_repository_refs(
    db: Session,
    repository: GitRepository,
    repository_path: Path,
    key_logs: list[str],
) -> None:
    credential = get_gitlab_credential(db, repository.workspace_id)
    auth_env = git_auth_env(credential, repository.remote_url)

    set_url = run_git(
        ["git", "-C", str(repository_path), "remote", "set-url", "origin", repository.remote_url],
        repository.sync_timeout_seconds,
        key_logs,
    )
    if set_url.returncode != 0:
        stderr = set_url.stderr.strip()[:500] or f"git exited with {set_url.returncode}"
        raise RuntimeError(stderr)

    fetch = run_git(
        ["git", "-C", str(repository_path), "fetch", "--prune", "--tags", "--force", "origin"],
        repository.sync_timeout_seconds,
        key_logs,
        env_overrides=auth_env,
    )
    fetch_output = "\n".join(part.strip() for part in (fetch.stdout, fetch.stderr) if part.strip())
    if fetch_output and fetch.returncode == 0:
        key_logs.append(fetch_output[:1000])
    if fetch.returncode != 0:
        stderr = fetch.stderr.strip()[:500] or f"git exited with {fetch.returncode}"
        raise RuntimeError(stderr)


def run_repository_sync(database: Database, settings: Settings, job_id: str) -> None:
    with database.session_factory() as db:
        job = db.get(Job, job_id)
        if job is None:
            return
        repository = db.get(GitRepository, job.repository_id)
        if repository is None:
            job.status = JobStatus.failed.value
            job.error_summary = "Repository no longer exists"
            job.finished_at = now_utc()
            db.commit()
            return

        job.status = JobStatus.running.value
        job.started_at = now_utc()
        job.key_logs = [f"Sandbox root: {settings.git_sandbox_root}", "Git sync started"]
        db.commit()

        try:
            root = Path(settings.git_sandbox_root).expanduser()
            repository_path = ensure_safe_sandbox_path(
                root,
                sandbox_path(settings, repository.workspace_id, repository.project_id, repository.id),
            )
            previous_path = None
            if repository.mirror_path and repository.mirror_path != "pending":
                previous_path = ensure_safe_sandbox_path(root, Path(repository.mirror_path))
            repository_path.parent.mkdir(parents=True, exist_ok=True)

            if repository_path.exists() and is_full_checkout(repository_path):
                refresh_repository_refs(db, repository, repository_path, job.key_logs)
                result = subprocess.CompletedProcess([], 0, stdout="", stderr="")
            else:
                if repository_path.exists():
                    remove_tree_readonly(repository_path)
                command = ["git", "clone", "--no-single-branch", "--", repository.remote_url, str(repository_path)]
                credential = get_gitlab_credential(db, repository.workspace_id)
                auth_env = git_auth_env(credential, repository.remote_url)
                result = run_git(command, repository.sync_timeout_seconds, job.key_logs, env_overrides=auth_env)
            if result.stdout.strip():
                job.key_logs = [*job.key_logs, result.stdout.strip()[:1000]]
            if result.returncode != 0:
                stderr = result.stderr.strip()[:500] or f"git exited with {result.returncode}"
                raise RuntimeError(stderr)
            checkout_default_branch(repository_path, repository.default_branch, repository.sync_timeout_seconds, job.key_logs)

            size_mb = directory_size_mb(repository_path)
            job.key_logs = [*job.key_logs, f"Repository checkout size: {size_mb:.2f} MB"]
            if size_mb > repository.repo_size_limit_mb:
                raise RuntimeError(f"Repository checkout exceeds {repository.repo_size_limit_mb} MB limit")

            if previous_path is not None and previous_path != repository_path and previous_path.exists():
                remove_tree_readonly(previous_path)
            repository.mirror_path = str(repository_path)
            repository.status = RepositoryStatus.synced.value
            repository.last_synced_at = now_utc()
            repository.updated_at = now_utc()
            job.status = JobStatus.succeeded.value
            job.output_summary = f"Repository checkout synced to {repository_path}"
        except subprocess.TimeoutExpired:
            repository.status = RepositoryStatus.sync_failed.value
            job.status = JobStatus.failed.value
            job.error_summary = f"Git sync timed out after {repository.sync_timeout_seconds} seconds"
        except Exception as exc:
            repository.status = RepositoryStatus.sync_failed.value
            job.status = JobStatus.failed.value
            job.error_summary = str(exc)[:500]
        finally:
            job.finished_at = now_utc()
            db.commit()


