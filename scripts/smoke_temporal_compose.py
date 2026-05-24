from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any
from uuid import uuid4


ACTOR_EMAIL = "owner@qualiforge.local"


@dataclass(frozen=True)
class SmokeContext:
    api_base: str
    actor_email: str
    suffix: str


def request_json(method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - local smoke target.
            response_body = response.read().decode("utf-8")
            return json.loads(response_body) if response_body else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed with {exc.code}: {detail}") from exc


def wait_for(label: str, timeout_seconds: int, probe):
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            result = probe()
            if result:
                return result
        except Exception as exc:  # noqa: BLE001 - smoke keeps last failure for diagnostics.
            last_error = exc
        time.sleep(1)
    if last_error is not None:
        raise TimeoutError(f"Timed out waiting for {label}: {last_error}") from last_error
    raise TimeoutError(f"Timed out waiting for {label}")


def with_actor(path: str, actor_email: str) -> str:
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}actor_email={urllib.parse.quote(actor_email)}"


def run_compose_exec(command: str) -> None:
    subprocess.run(
        ["docker", "compose", "exec", "-T", "backend", "sh", "-lc", command],
        check=True,
    )


def seed_container_git_repo(suffix: str) -> str:
    repo_path = f"/data/imports/agent-temporal-smoke-src-{suffix}"
    command = f"""
set -eu
rm -rf {repo_path}
mkdir -p {repo_path}/src
cd {repo_path}
git init -q
git config user.email smoke@qualiforge.local
git config user.name 'QualiForge Smoke'
cat > src/refund_audit.py <<'PY'
def record_refund_audit(event):
    if event.get("status") == "rejected":
        return "reviewer evidence required"
    return "accepted"
PY
cat > README.md <<'MD'
# Agent Temporal Smoke

Refund audit fixture repository for the durable agent workflow smoke test.
MD
git add .
git commit -q -m 'seed refund audit fixture'
"""
    run_compose_exec(command)
    return repo_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test the Docker Compose Temporal agent path.")
    parser.add_argument("--api-base", default="http://localhost:8000/api")
    parser.add_argument("--actor-email", default=ACTOR_EMAIL)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    context = SmokeContext(api_base=args.api_base.rstrip("/"), actor_email=args.actor_email, suffix=uuid4().hex[:8])

    wait_for(
        "backend health",
        args.timeout,
        lambda: request_json("GET", f"{context.api_base}/health").get("status") == "ok",
    )
    repo_path = seed_container_git_repo(context.suffix)

    workspace = request_json(
        "POST",
        f"{context.api_base}/workspaces",
        {
            "name": f"Temporal Smoke {context.suffix}",
            "owner_email": context.actor_email,
            "owner_display_name": "Temporal Smoke",
        },
    )
    project = request_json(
        "POST",
        f"{context.api_base}{with_actor(f'/workspaces/{workspace['id']}/projects', context.actor_email)}",
        {
            "name": "Temporal Agent Smoke",
            "key": f"TS{context.suffix[:6].upper()}",
            "description": "Docker Compose Temporal agent smoke project",
        },
    )
    repository = request_json(
        "POST",
        f"{context.api_base}{with_actor(f'/workspaces/{workspace['id']}/repositories', context.actor_email)}",
        {
            "project_id": project["id"],
            "name": "Temporal smoke fixture",
            "remote_url": repo_path,
            "default_branch": "master",
            "repo_size_limit_mb": 100,
            "diff_file_limit": 100,
            "sync_timeout_seconds": 30,
        },
    )
    sync_job = request_json(
        "POST",
        f"{context.api_base}{with_actor(f'/workspaces/{workspace['id']}/repositories/{repository['id']}/sync', context.actor_email)}",
    )

    def synced_job() -> dict[str, Any] | None:
        jobs = request_json(
            "GET",
            f"{context.api_base}/workspaces/{workspace['id']}/jobs?repository_id={repository['id']}",
        )
        for job in jobs:
            if job["id"] == sync_job["id"]:
                if job["status"] == "succeeded":
                    return job
                if job["status"] == "failed":
                    raise RuntimeError(f"repository sync failed: {job['error_summary']}")
        return None

    wait_for("repository sync", args.timeout, synced_job)

    conversation = request_json(
        "POST",
        f"{context.api_base}{with_actor(f'/workspaces/{workspace['id']}/agent/conversations', context.actor_email)}",
        {"project_id": project["id"], "title": "Temporal smoke conversation"},
    )
    run = request_json(
        "POST",
        f"{context.api_base}{with_actor(f'/workspaces/{workspace['id']}/agent/conversations/{conversation['id']}/runs', context.actor_email)}",
        {
            "project_id": project["id"],
            "goal": "Generate refund audit candidate cases through the Temporal workflow",
            "mode": "execute",
            "trigger_type": "compose_smoke",
            "budget_snapshot": {
                "max_tool_calls": 40,
                "max_model_calls": 0,
                "max_subagents": 4,
                "max_parallel_subagents": 3,
                "max_case_candidates_per_run": 3,
                "max_wall_time_minutes": 5,
                "max_total_source_chars_sent": 20000,
            },
        },
    )
    execute = request_json(
        "POST",
        f"{context.api_base}{with_actor(f'/workspaces/{workspace['id']}/agent/runs/{run['id']}/execute', context.actor_email)}",
        {"repository_id": repository["id"], "ref": "master", "candidate_limit": 3},
    )
    if execute["run"]["temporal_workflow_id"] != f"agent-run-{run['id']}":
        raise RuntimeError(f"unexpected workflow id: {execute['run']['temporal_workflow_id']}")

    def waiting_detail() -> dict[str, Any] | None:
        detail = request_json(
            "GET",
            f"{context.api_base}/workspaces/{workspace['id']}/agent/runs/{run['id']}/execution-detail",
        )
        status = detail["run"]["status"]
        if status == "waiting_for_user":
            return detail
        if status in {"failed", "cancelled", "succeeded"}:
            raise RuntimeError(f"run reached unexpected terminal status {status}: {detail['run']['failure_reason']}")
        return None

    detail = wait_for("agent run waiting for budget", args.timeout, waiting_detail)
    if "model budget exceeded" not in detail["run"]["failure_reason"]:
        raise RuntimeError(f"unexpected waiting reason: {detail['run']['failure_reason']}")

    resume = request_json(
        "POST",
        f"{context.api_base}{with_actor(f'/workspaces/{workspace['id']}/agent/runs/{run['id']}/resume', context.actor_email)}",
        {
            "budget_snapshot": {"max_model_calls": 0},
            "resume_reason": "Smoke resume signal without enabling model calls",
        },
    )
    if "resume signal" not in resume["summary"]:
        raise RuntimeError(f"resume did not signal workflow: {resume['summary']}")

    detail_url = f"{context.api_base}/workspaces/{workspace['id']}/agent/runs/{run['id']}/execution-detail"
    request_json(
        "POST",
        f"{context.api_base}{with_actor(f'/workspaces/{workspace['id']}/agent/runs/{run['id']}/cancel', context.actor_email)}",
        {"cancel_reason": "Smoke cancellation after resume signal"},
    )

    def cancelled_detail() -> dict[str, Any] | None:
        detail = request_json("GET", detail_url)
        return detail if detail["run"]["status"] == "cancelled" else None

    cancelled = wait_for(
        "agent run cancelled",
        args.timeout,
        cancelled_detail,
    )

    print(
        json.dumps(
            {
                "status": "ok",
                "workspace_id": workspace["id"],
                "project_id": project["id"],
                "repository_id": repository["id"],
                "run_id": run["id"],
                "workflow_id": execute["run"]["temporal_workflow_id"],
                "final_status": cancelled["run"]["status"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
