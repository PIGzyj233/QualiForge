from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.agents import AgentRun, AgentRunStatus
from app.config import Settings
from app.main import create_app
from app.model_gateway import RetryableModelGatewayError


OWNER = "owner@qualiforge.local"


def make_client(
    tmp_path: Path | None = None,
    model_gateway_transport: Callable | None = None,
    settings_overrides: dict[str, Any] | None = None,
) -> TestClient:
    settings_values = {
        "_env_file": None,
        "database_url": "sqlite+pysqlite:///:memory:",
        "redis_url": "redis://localhost:6379/15",
        "git_sandbox_root": str(tmp_path / "sandbox") if tmp_path else ".qualiforge/test-git-sandbox",
        "git_sync_timeout_seconds": 30,
        "git_repo_size_limit_mb": 128,
        "git_diff_file_limit": 250,
        "model_gateway_api_key": "dev-litellm-key",
    }
    settings_values.update(settings_overrides or {})
    settings = Settings(**settings_values)
    app = create_app(settings)
    if model_gateway_transport is not None:
        app.state.model_gateway_transport = model_gateway_transport
    return TestClient(app)


def create_workspace_project(client: TestClient) -> tuple[dict, dict]:
    workspace_response = client.post(
        "/api/workspaces",
        json={
            "name": "Agent Lab",
            "owner_email": OWNER,
            "owner_display_name": "Workspace Owner",
        },
    )
    assert workspace_response.status_code == 201
    workspace = workspace_response.json()
    project_response = client.post(
        f"/api/workspaces/{workspace['id']}/projects?actor_email={OWNER}",
        json={"name": "Checkout", "key": "CHECKOUT", "description": "Checkout regression surface"},
    )
    assert project_response.status_code == 201
    return workspace, project_response.json()


def git_run(repo: Path, args: list[str]) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def create_refund_fixture_repo(tmp_path: Path) -> Path:
    if shutil.which("git") is None:
        pytest.skip("git executable is not available")

    source = tmp_path / "agent-source"
    (source / "src" / "checkout").mkdir(parents=True)
    git_run(tmp_path, ["init", "--initial-branch=master", str(source)])
    git_run(source, ["config", "user.email", "tester@qualiforge.local"])
    git_run(source, ["config", "user.name", "QualiForge Tester"])
    (source / "src" / "checkout" / "refund.py").write_text(
        "\n".join(
            [
                "import logging",
                "",
                "logger = logging.getLogger(__name__)",
                "",
                "def refund_order(order_id, actor):",
                "    refund_id = f'refund-{order_id}'",
                "    audit_event = 'refund.created'",
                "    logger.info('refund_id=%s order_id=%s actor=%s', refund_id, order_id, actor)",
                "    return {'status': 'refunded', 'audit_event': audit_event, 'refund_id': refund_id}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    git_run(source, ["add", "."])
    git_run(source, ["commit", "-m", "refund audit signal"])
    return source


def bind_repository(client: TestClient, workspace_id: str, project_id: str, source: Path) -> dict:
    response = client.post(
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
    assert response.status_code == 201
    return response.json()


def sync_repository(client: TestClient, workspace_id: str, project_id: str, repository_id: str) -> dict:
    sync_response = client.post(f"/api/workspaces/{workspace_id}/repositories/{repository_id}/sync?actor_email={OWNER}")
    assert sync_response.status_code == 202
    synced = client.get(f"/api/workspaces/{workspace_id}/repositories?project_id={project_id}").json()[0]
    assert synced["status"] == "synced"
    return synced


def create_agent_run(
    client: TestClient,
    workspace_id: str,
    project_id: str,
    *,
    mode: str = "execute",
    budget_snapshot: dict[str, Any] | None = None,
) -> dict:
    conversation = client.post(
        f"/api/workspaces/{workspace_id}/agent/conversations?actor_email={OWNER}",
        json={"title": "Generate refund cases", "project_id": project_id},
    ).json()
    run_response = client.post(
        f"/api/workspaces/{workspace_id}/agent/conversations/{conversation['id']}/runs?actor_email={OWNER}",
        json={
            "goal": "Generate refund audit candidate cases with observability",
            "mode": mode,
            "budget_snapshot": budget_snapshot or {"max_tool_calls": 20},
        },
    )
    assert run_response.status_code == 201
    return run_response.json()


def case_candidate_content() -> str:
    return json.dumps(
        {
            "case_candidates": [
                {
                    "title": "Validate refund audit trail",
                    "steps": ["Create a paid order", "Trigger a refund", "Inspect audit history and refund logs"],
                    "expected_result": "Refund completes and refund.created audit evidence includes refund_id and order_id.",
                    "risk": "medium",
                    "priority": "P1",
                    "module_key": "CHECKOUT",
                    "unmapped_reason": "",
                    "observability": {
                        "signals": [],
                        "audit_events": ["refund.created"],
                        "log_keywords": ["refund_id", "order_id"],
                        "metrics": [],
                        "trace_points": [],
                        "job_states": [],
                        "entity_ids": [],
                        "gaps": [],
                    },
                    "evidence_refs": [
                        {
                            "kind": "code_file",
                            "ref_id": "repo:HEAD:src/checkout/refund.py",
                            "label": "src/checkout/refund.py:5-9",
                            "summary": "Refund flow emits refund.created and logs refund/order identifiers.",
                            "confidence": 0.9,
                            "source": "code_read_range",
                        }
                    ],
                    "duplicate_result": {"classification": "coverage_gap", "reason": "No existing staged or formal coverage matched refund audit."},
                    "coverage_entries": [
                        {
                            "module_key": "CHECKOUT",
                            "behavior_summary": "Refund emits attributable audit and log signals.",
                            "signals": [
                                {"signal_type": "audit_event", "value": "refund.created", "source": "agent_inferred", "confidence": 90}
                            ],
                            "evidence_refs": [
                                {
                                    "kind": "code_file",
                                    "ref_id": "repo:HEAD:src/checkout/refund.py",
                                    "label": "src/checkout/refund.py:5-9",
                                }
                            ],
                            "confidence": 90,
                        }
                    ],
                }
            ]
        }
    )


def successful_model_transport(calls: list[dict[str, Any]]) -> Callable:
    def fake_transport(url: str, headers: dict[str, str], payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        calls.append({"url": url, "headers": headers, "payload": payload, "timeout": timeout_seconds})
        return {
            "id": "chatcmpl-agent-test",
            "model": payload["model"],
            "choices": [{"message": {"content": case_candidate_content()}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 80},
        }

    return fake_transport


def test_agent_conversation_run_staged_output_and_coverage_flow() -> None:
    client = make_client()
    workspace, project = create_workspace_project(client)

    conversation_response = client.post(
        f"/api/workspaces/{workspace['id']}/agent/conversations?actor_email={OWNER}",
        json={"title": "Generate checkout cases", "project_id": project["id"]},
    )
    assert conversation_response.status_code == 201
    conversation = conversation_response.json()
    assert conversation["project_id"] == project["id"]

    message_response = client.post(
        f"/api/workspaces/{workspace['id']}/agent/conversations/{conversation['id']}/messages?actor_email={OWNER}",
        json={"role": "user", "content": "分析 refund diff 并生成候选用例", "metadata": {"mode": "execute"}},
    )
    assert message_response.status_code == 201
    assert message_response.json()["metadata"] == {"mode": "execute"}

    run_response = client.post(
        f"/api/workspaces/{workspace['id']}/agent/conversations/{conversation['id']}/runs?actor_email={OWNER}",
        json={
            "goal": "Generate non-duplicate refund case candidates with observability signals",
            "mode": "execute",
            "budget_snapshot": {"max_tool_calls": 60, "max_subagents": 4},
        },
    )
    assert run_response.status_code == 201
    run = run_response.json()
    assert run["mode"] == "execute"
    assert run["project_id"] == project["id"]

    staged_response = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/staged-outputs?actor_email={OWNER}",
        json={
            "output_type": "case_candidate",
            "title": "Validate checkout refund audit trail",
            "payload": {
                "steps": ["Create a paid order", "Trigger refund", "Open order audit history"],
                "expected_result": "Refund is visible to the operator and audit history records the actor.",
                "observability": {
                    "audit_events": ["refund.created"],
                    "log_keywords": ["refund_id", "order_id"],
                    "gaps": [],
                },
            },
            "evidence_refs": [
                {
                    "kind": "code_file",
                    "ref_id": "repo:v2:src/checkout/refund.py",
                    "label": "src/checkout/refund.py:20-64",
                    "summary": "Refund route records audit event.",
                    "confidence": 0.88,
                    "source": "code_search",
                }
            ],
            "quality_result": {"passed": True},
            "duplicate_result": {"classification": "coverage_gap"},
            "coverage_entries": [
                {
                    "module_key": "CHECKOUT",
                    "behavior_summary": "Refund audit trail is visible and attributable.",
                    "signals": [
                        {"signal_type": "audit_event", "value": "refund.created", "source": "agent_inferred", "confidence": 85}
                    ],
                    "evidence_refs": [
                        {
                            "kind": "code_file",
                            "ref_id": "repo:v2:src/checkout/refund.py",
                            "label": "src/checkout/refund.py:20-64",
                        }
                    ],
                    "confidence": 85,
                }
            ],
        },
    )
    assert staged_response.status_code == 201
    staged = staged_response.json()
    assert staged["status"] == "staged"
    assert staged["coverage_entries"][0]["coverage_state"] == "staged"
    assert staged["payload"]["observability"]["audit_events"] == ["refund.created"]

    accepted_response = client.patch(
        f"/api/workspaces/{workspace['id']}/agent/staged-outputs/{staged['id']}?actor_email={OWNER}",
        json={"status": "accepted", "decision_summary": "Looks useful for refund regression"},
    )
    assert accepted_response.status_code == 200
    accepted = accepted_response.json()
    assert accepted["status"] == "accepted"
    assert accepted["decision_summary"] == "Looks useful for refund regression"
    assert accepted["coverage_entries"][0]["coverage_state"] == "candidate"
    assert accepted["coverage_entries"][0]["verified_by_human"] is True

    coverage_response = client.get(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/coverage-index?coverage_state=candidate&module_key=CHECKOUT"
    )
    assert coverage_response.status_code == 200
    coverage = coverage_response.json()
    assert [entry["behavior_summary"] for entry in coverage] == ["Refund audit trail is visible and attributable."]

    audit_logs = client.get(f"/api/workspaces/{workspace['id']}/audit-logs").json()
    actions = [entry["action"] for entry in audit_logs]
    assert "agent_conversation.created" in actions
    assert "agent_run.created" in actions
    assert "agent_staged_output.created" in actions
    assert "agent_staged_output.accepted" in actions


def test_rejecting_staged_output_marks_coverage_rejected_and_blocks_second_decision() -> None:
    client = make_client()
    workspace, project = create_workspace_project(client)
    conversation = client.post(
        f"/api/workspaces/{workspace['id']}/agent/conversations?actor_email={OWNER}",
        json={"title": "Import cleanup", "project_id": project["id"]},
    ).json()
    run = client.post(
        f"/api/workspaces/{workspace['id']}/agent/conversations/{conversation['id']}/runs?actor_email={OWNER}",
        json={"goal": "Preview duplicate imported cases", "mode": "execute"},
    ).json()
    staged = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/staged-outputs?actor_email={OWNER}",
        json={
            "output_type": "case_candidate",
            "title": "Duplicate checkout smoke case",
            "coverage_entries": [{"module_key": "CHECKOUT", "behavior_summary": "Checkout smoke flow"}],
        },
    ).json()

    rejected_response = client.patch(
        f"/api/workspaces/{workspace['id']}/agent/staged-outputs/{staged['id']}?actor_email={OWNER}",
        json={"status": "rejected", "decision_summary": "Already covered by formal case"},
    )
    assert rejected_response.status_code == 200
    assert rejected_response.json()["coverage_entries"][0]["coverage_state"] == "rejected"

    second_decision = client.patch(
        f"/api/workspaces/{workspace['id']}/agent/staged-outputs/{staged['id']}?actor_email={OWNER}",
        json={"status": "accepted"},
    )
    assert second_decision.status_code == 409


def test_preview_run_cannot_create_staged_output() -> None:
    client = make_client()
    workspace, project = create_workspace_project(client)
    conversation = client.post(
        f"/api/workspaces/{workspace['id']}/agent/conversations?actor_email={OWNER}",
        json={"title": "Read-only agent preview", "project_id": project["id"]},
    ).json()
    run = client.post(
        f"/api/workspaces/{workspace['id']}/agent/conversations/{conversation['id']}/runs?actor_email={OWNER}",
        json={"goal": "Preview duplicate coverage only", "mode": "preview"},
    ).json()

    response = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/staged-outputs?actor_email={OWNER}",
        json={
            "output_type": "case_candidate",
            "title": "Should remain read-only",
            "coverage_entries": [{"module_key": "CHECKOUT", "behavior_summary": "Preview-only signal"}],
        },
    )

    assert response.status_code == 409
    assert "execute agent run" in response.json()["detail"]


def test_agent_execute_requires_synced_repository(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    workspace, project = create_workspace_project(client)
    source = create_refund_fixture_repo(tmp_path)
    repository = bind_repository(client, workspace["id"], project["id"], source)
    run = create_agent_run(client, workspace["id"], project["id"])

    response = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execute?actor_email={OWNER}",
        json={"repository_id": repository["id"], "ref": "master"},
    )

    assert response.status_code == 409
    assert "synced" in response.json()["detail"]


def test_agent_execute_creates_worktree_and_tool_audit(tmp_path: Path) -> None:
    model_calls: list[dict[str, Any]] = []
    client = make_client(tmp_path, successful_model_transport(model_calls))
    workspace, project = create_workspace_project(client)
    source = create_refund_fixture_repo(tmp_path)
    repository = bind_repository(client, workspace["id"], project["id"], source)
    repository = sync_repository(client, workspace["id"], project["id"], repository["id"])
    run = create_agent_run(client, workspace["id"], project["id"])

    response = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execute?actor_email={OWNER}",
        json={"repository_id": repository["id"], "ref": "master"},
    )

    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload["run"]["status"] == "succeeded"
    assert payload["sandboxes"][0]["status"] == "cleaned"
    assert "agent-worktrees" in payload["sandboxes"][0]["worktree_path"]
    assert not Path(payload["sandboxes"][0]["worktree_path"]).exists()
    tool_names = [item["tool_name"] for item in payload["tool_calls"]]
    assert "coverage_lookup" in tool_names
    assert "code_search" in tool_names
    assert "code_read_range" in tool_names
    assert model_calls[0]["url"] == "http://litellm:4000/v1/chat/completions"
    assert model_calls[0]["payload"]["model"] == "qf-supervisor-strong"
    assert "dev-litellm-key" not in str(payload)

    invocations = client.get(f"/api/workspaces/{workspace['id']}/ai-invocations").json()
    assert invocations[0]["agent_run_id"] == run["id"]
    assert invocations[0]["provider_name"] == "litellm"
    assert invocations[0]["model_alias"] == "qf-supervisor-strong"
    assert invocations[0]["attempts"] == 1
    assert invocations[0]["usage"] == {"prompt_tokens": 120, "completion_tokens": 80}


def test_agent_execute_generates_staged_case_candidate(tmp_path: Path) -> None:
    model_calls: list[dict[str, Any]] = []
    client = make_client(tmp_path, successful_model_transport(model_calls))
    workspace, project = create_workspace_project(client)
    source = create_refund_fixture_repo(tmp_path)
    repository = bind_repository(client, workspace["id"], project["id"], source)
    repository = sync_repository(client, workspace["id"], project["id"], repository["id"])
    run = create_agent_run(client, workspace["id"], project["id"])

    response = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execute?actor_email={OWNER}",
        json={"repository_id": repository["id"], "ref": "master"},
    )

    assert response.status_code == 200, response.json()
    staged = response.json()["staged_outputs"][0]
    assert staged["output_type"] == "case_candidate"
    assert staged["status"] == "staged"
    assert staged["payload"]["observability"]["audit_events"] == ["refund.created"]
    assert staged["payload"]["risk"] == "medium"
    assert staged["payload"]["priority"] == "P1"
    assert staged["payload"]["module_key"] == "CHECKOUT"
    assert staged["duplicate_result"]["classification"] == "coverage_gap"
    assert staged["duplicate_result"]["source"] == "deterministic_lookup"
    assert staged["evidence_refs"][0]["kind"] == "code_file"
    assert staged["coverage_entries"][0]["coverage_state"] == "staged"
    assert staged["coverage_entries"][0]["module_key"] == "CHECKOUT"

    coverage = client.get(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/coverage-index?coverage_state=staged&module_key=CHECKOUT"
    ).json()
    assert [entry["behavior_summary"] for entry in coverage] == ["Refund emits attributable audit and log signals."]


def test_agent_execute_is_idempotent_for_same_run_ref(tmp_path: Path) -> None:
    model_calls: list[dict[str, Any]] = []
    client = make_client(tmp_path, successful_model_transport(model_calls))
    workspace, project = create_workspace_project(client)
    source = create_refund_fixture_repo(tmp_path)
    repository = bind_repository(client, workspace["id"], project["id"], source)
    repository = sync_repository(client, workspace["id"], project["id"], repository["id"])
    run = create_agent_run(client, workspace["id"], project["id"])
    url = f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execute?actor_email={OWNER}"

    first = client.post(url, json={"repository_id": repository["id"], "ref": "master"})
    second = client.post(url, json={"repository_id": repository["id"], "ref": "master"})

    assert first.status_code == 200, first.json()
    assert second.status_code == 200, second.json()
    assert second.json()["run"]["status"] == "succeeded"
    assert "already succeeded" in second.json()["summary"]
    assert len(model_calls) == 1
    assert len(second.json()["staged_outputs"]) == 1
    coverage = client.get(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/coverage-index?coverage_state=staged&module_key=CHECKOUT"
    ).json()
    assert len(coverage) == 1


def test_agent_execute_writes_reuse_note_for_existing_coverage(tmp_path: Path) -> None:
    model_calls: list[dict[str, Any]] = []
    client = make_client(tmp_path, successful_model_transport(model_calls))
    workspace, project = create_workspace_project(client)
    seed_run = create_agent_run(client, workspace["id"], project["id"])
    seed = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{seed_run['id']}/staged-outputs?actor_email={OWNER}",
        json={
            "output_type": "case_candidate",
            "title": "Existing refund audit coverage",
            "payload": {
                "steps": ["Create a paid order", "Trigger refund"],
                "expected_result": "Refund emits attributable audit and log signals.",
                "module_key": "CHECKOUT",
            },
            "coverage_entries": [
                {
                    "module_key": "CHECKOUT",
                    "behavior_summary": "Refund emits attributable audit and log signals.",
                    "signals": [{"signal_type": "audit_event", "value": "refund.created", "source": "seed"}],
                }
            ],
        },
    )
    assert seed.status_code == 201
    source = create_refund_fixture_repo(tmp_path)
    repository = bind_repository(client, workspace["id"], project["id"], source)
    repository = sync_repository(client, workspace["id"], project["id"], repository["id"])
    run = create_agent_run(client, workspace["id"], project["id"])

    response = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execute?actor_email={OWNER}",
        json={"repository_id": repository["id"], "ref": "master"},
    )

    assert response.status_code == 200, response.json()
    outputs = response.json()["staged_outputs"]
    assert [item["output_type"] for item in outputs] == ["agent_note"]
    assert outputs[0]["duplicate_result"]["classification"] == "high_confidence_duplicate"
    assert outputs[0]["payload"]["recommendation"] == "reuse_existing_coverage"


def test_agent_execute_waits_when_model_budget_exceeded(tmp_path: Path) -> None:
    model_calls: list[dict[str, Any]] = []
    client = make_client(tmp_path, successful_model_transport(model_calls))
    workspace, project = create_workspace_project(client)
    source = create_refund_fixture_repo(tmp_path)
    repository = bind_repository(client, workspace["id"], project["id"], source)
    repository = sync_repository(client, workspace["id"], project["id"], repository["id"])
    run = create_agent_run(
        client,
        workspace["id"],
        project["id"],
        budget_snapshot={"max_tool_calls": 20, "max_model_calls": 0},
    )

    response = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execute?actor_email={OWNER}",
        json={"repository_id": repository["id"], "ref": "master"},
    )

    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload["run"]["status"] == "waiting_for_user"
    assert "model budget exceeded" in payload["run"]["failure_reason"]
    assert payload["staged_outputs"] == []
    assert model_calls == []


def test_agent_execute_rejects_when_ai_disabled(tmp_path: Path) -> None:
    model_calls: list[dict[str, Any]] = []
    client = make_client(tmp_path, successful_model_transport(model_calls))
    workspace, project = create_workspace_project(client)
    policy_response = client.put(
        f"/api/workspaces/{workspace['id']}/ai-settings?actor_email={OWNER}",
        json={"data_policy": "AIDisabled"},
    )
    assert policy_response.status_code == 200
    source = create_refund_fixture_repo(tmp_path)
    repository = bind_repository(client, workspace["id"], project["id"], source)
    repository = sync_repository(client, workspace["id"], project["id"], repository["id"])
    run = create_agent_run(client, workspace["id"], project["id"])

    response = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execute?actor_email={OWNER}",
        json={"repository_id": repository["id"], "ref": "master"},
    )

    assert response.status_code == 403
    assert "disabled" in response.json()["detail"]
    assert model_calls == []
    invocations = client.get(f"/api/workspaces/{workspace['id']}/ai-invocations").json()
    assert invocations[0]["status"] == "rejected"
    assert invocations[0]["data_policy"] == "AIDisabled"
    assert invocations[0]["agent_run_id"] == run["id"]


def test_agent_execute_rejects_source_code_when_no_source_code_policy(tmp_path: Path) -> None:
    model_calls: list[dict[str, Any]] = []
    client = make_client(tmp_path, successful_model_transport(model_calls))
    workspace, project = create_workspace_project(client)
    client.put(
        f"/api/workspaces/{workspace['id']}/ai-settings?actor_email={OWNER}",
        json={"data_policy": "NoSourceCode"},
    )
    source = create_refund_fixture_repo(tmp_path)
    repository = bind_repository(client, workspace["id"], project["id"], source)
    repository = sync_repository(client, workspace["id"], project["id"], repository["id"])
    run = create_agent_run(client, workspace["id"], project["id"])

    response = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execute?actor_email={OWNER}",
        json={"repository_id": repository["id"], "ref": "master"},
    )

    assert response.status_code == 403
    assert "source code" in response.json()["detail"]
    assert model_calls == []
    invocations = client.get(f"/api/workspaces/{workspace['id']}/ai-invocations").json()
    assert invocations[0]["input_data_types"] == [
        "goal",
        "coverage_index",
        "code_tool_observations",
        "source_code",
        "source_code_excerpt",
    ]
    assert invocations[0]["includes_source_code"] is True


def test_agent_execute_allows_internal_litellm_under_internal_only(tmp_path: Path) -> None:
    model_calls: list[dict[str, Any]] = []
    client = make_client(tmp_path, successful_model_transport(model_calls))
    workspace, project = create_workspace_project(client)
    client.put(
        f"/api/workspaces/{workspace['id']}/ai-settings?actor_email={OWNER}",
        json={"data_policy": "InternalOnly"},
    )
    source = create_refund_fixture_repo(tmp_path)
    repository = bind_repository(client, workspace["id"], project["id"], source)
    repository = sync_repository(client, workspace["id"], project["id"], repository["id"])
    run = create_agent_run(client, workspace["id"], project["id"])

    response = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execute?actor_email={OWNER}",
        json={"repository_id": repository["id"], "ref": "master"},
    )

    assert response.status_code == 200, response.json()
    assert response.json()["run"]["status"] == "succeeded"
    assert model_calls[0]["url"] == "http://litellm:4000/v1/chat/completions"
    invocations = client.get(f"/api/workspaces/{workspace['id']}/ai-invocations").json()
    assert invocations[0]["data_policy"] == "InternalOnly"


def test_agent_execute_rejects_external_gateway_under_internal_only(tmp_path: Path) -> None:
    model_calls: list[dict[str, Any]] = []
    client = make_client(
        tmp_path,
        successful_model_transport(model_calls),
        settings_overrides={"model_gateway_api_base_url": "https://api.openai.com/v1"},
    )
    workspace, project = create_workspace_project(client)
    client.put(
        f"/api/workspaces/{workspace['id']}/ai-settings?actor_email={OWNER}",
        json={"data_policy": "InternalOnly"},
    )
    source = create_refund_fixture_repo(tmp_path)
    repository = bind_repository(client, workspace["id"], project["id"], source)
    repository = sync_repository(client, workspace["id"], project["id"], repository["id"])
    run = create_agent_run(client, workspace["id"], project["id"])

    response = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execute?actor_email={OWNER}",
        json={"repository_id": repository["id"], "ref": "master"},
    )

    assert response.status_code == 403
    assert "internal model gateway" in response.json()["detail"]
    assert model_calls == []


def test_agent_invocation_log_records_policy_without_prompt_or_secret(tmp_path: Path) -> None:
    model_calls: list[dict[str, Any]] = []
    client = make_client(tmp_path, successful_model_transport(model_calls))
    workspace, project = create_workspace_project(client)
    source = create_refund_fixture_repo(tmp_path)
    repository = bind_repository(client, workspace["id"], project["id"], source)
    repository = sync_repository(client, workspace["id"], project["id"], repository["id"])
    run = create_agent_run(client, workspace["id"], project["id"])

    response = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execute?actor_email={OWNER}",
        json={"repository_id": repository["id"], "ref": "master"},
    )

    assert response.status_code == 200, response.json()
    invocations = client.get(f"/api/workspaces/{workspace['id']}/ai-invocations").json()
    invocation = invocations[0]
    assert invocation["data_policy"] == "ExternalAllowed"
    assert "source_code" in invocation["input_data_types"]
    assert invocation["includes_source_code"] is True
    serialized_invocation = json.dumps(invocation)
    assert "dev-litellm-key" not in serialized_invocation
    assert "refund_order" not in serialized_invocation
    assert run["goal"] not in serialized_invocation


def test_succeeded_run_different_ref_conflicts(tmp_path: Path) -> None:
    model_calls: list[dict[str, Any]] = []
    client = make_client(tmp_path, successful_model_transport(model_calls))
    workspace, project = create_workspace_project(client)
    source = create_refund_fixture_repo(tmp_path)
    repository = bind_repository(client, workspace["id"], project["id"], source)
    repository = sync_repository(client, workspace["id"], project["id"], repository["id"])
    run = create_agent_run(client, workspace["id"], project["id"])
    url = f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execute?actor_email={OWNER}"

    first = client.post(url, json={"repository_id": repository["id"], "ref": "master"})
    second = client.post(url, json={"repository_id": repository["id"], "ref": "HEAD"})

    assert first.status_code == 200, first.json()
    assert second.status_code == 409
    assert "different repository/ref" in second.json()["detail"]
    assert len(model_calls) == 1


def test_running_run_cannot_execute_again(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    workspace, project = create_workspace_project(client)
    source = create_refund_fixture_repo(tmp_path)
    repository = bind_repository(client, workspace["id"], project["id"], source)
    repository = sync_repository(client, workspace["id"], project["id"], repository["id"])
    run = create_agent_run(client, workspace["id"], project["id"])
    with client.app.state.database.session_factory() as db:
        stored = db.get(AgentRun, run["id"])
        assert stored is not None
        stored.status = AgentRunStatus.running.value
        db.commit()

    response = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execute?actor_email={OWNER}",
        json={"repository_id": repository["id"], "ref": "master"},
    )

    assert response.status_code == 409
    assert "already running" in response.json()["detail"]


def test_agent_resume_from_model_budget_waiting_succeeds_and_audits_override(tmp_path: Path) -> None:
    model_calls: list[dict[str, Any]] = []
    client = make_client(tmp_path, successful_model_transport(model_calls))
    workspace, project = create_workspace_project(client)
    source = create_refund_fixture_repo(tmp_path)
    repository = bind_repository(client, workspace["id"], project["id"], source)
    repository = sync_repository(client, workspace["id"], project["id"], repository["id"])
    run = create_agent_run(
        client,
        workspace["id"],
        project["id"],
        budget_snapshot={"max_tool_calls": 20, "max_model_calls": 0},
    )

    waiting = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execute?actor_email={OWNER}",
        json={"repository_id": repository["id"], "ref": "master"},
    )
    resumed = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/resume?actor_email={OWNER}",
        json={
            "budget_snapshot": {"max_tool_calls": 40, "max_model_calls": 5, "max_case_candidates_per_run": 3},
            "resume_reason": "Allow model generation after reviewing budget",
        },
    )

    assert waiting.status_code == 200, waiting.json()
    assert waiting.json()["run"]["status"] == "waiting_for_user"
    assert resumed.status_code == 200, resumed.json()
    payload = resumed.json()
    assert payload["run"]["status"] == "succeeded"
    assert payload["staged_outputs"][0]["status"] == "staged"
    assert len(model_calls) == 1
    assert payload["run"]["budget_snapshot"]["max_model_calls"] == 5
    assert payload["run"]["budget_snapshot"]["usage"]["model_calls"] == 1
    audit_logs = client.get(f"/api/workspaces/{workspace['id']}/audit-logs").json()
    actions = [entry["action"] for entry in audit_logs]
    assert "agent_run.budget_overridden" in actions


def test_agent_cancel_waiting_run_and_cancelled_run_cannot_execute_or_resume(tmp_path: Path) -> None:
    model_calls: list[dict[str, Any]] = []
    client = make_client(tmp_path, successful_model_transport(model_calls))
    workspace, project = create_workspace_project(client)
    source = create_refund_fixture_repo(tmp_path)
    repository = bind_repository(client, workspace["id"], project["id"], source)
    repository = sync_repository(client, workspace["id"], project["id"], repository["id"])
    run = create_agent_run(
        client,
        workspace["id"],
        project["id"],
        budget_snapshot={"max_tool_calls": 20, "max_model_calls": 0},
    )
    waiting = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execute?actor_email={OWNER}",
        json={"repository_id": repository["id"], "ref": "master"},
    )
    cancelled = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/cancel?actor_email={OWNER}",
        json={"cancel_reason": "Stop budget expansion"},
    )
    execute_again = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execute?actor_email={OWNER}",
        json={"repository_id": repository["id"], "ref": "master"},
    )
    resume = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/resume?actor_email={OWNER}",
        json={"budget_snapshot": {"max_model_calls": 5}, "resume_reason": "Try after cancel"},
    )

    assert waiting.status_code == 200, waiting.json()
    assert cancelled.status_code == 200, cancelled.json()
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["cancelled_at"] is not None
    assert execute_again.status_code == 409
    assert "Cancelled" in execute_again.json()["detail"]
    assert resume.status_code == 409
    assert "Cancelled" in resume.json()["detail"]
    assert model_calls == []


def test_agent_execution_detail_includes_tool_calls_invocations_outputs_and_budget(tmp_path: Path) -> None:
    model_calls: list[dict[str, Any]] = []
    client = make_client(tmp_path, successful_model_transport(model_calls))
    workspace, project = create_workspace_project(client)
    source = create_refund_fixture_repo(tmp_path)
    repository = bind_repository(client, workspace["id"], project["id"], source)
    repository = sync_repository(client, workspace["id"], project["id"], repository["id"])
    run = create_agent_run(client, workspace["id"], project["id"])

    executed = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execute?actor_email={OWNER}",
        json={"repository_id": repository["id"], "ref": "master"},
    )
    detail = client.get(f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execution-detail")

    assert executed.status_code == 200, executed.json()
    assert detail.status_code == 200, detail.json()
    payload = detail.json()
    assert payload["run"]["status"] == "succeeded"
    assert payload["staged_outputs"][0]["output_type"] == "case_candidate"
    assert {item["tool_name"] for item in payload["tool_calls"]} >= {"coverage_lookup", "code_search"}
    assert payload["ai_invocations"][0]["status"] == "succeeded"
    assert payload["repository_sandboxes"][0]["status"] == "cleaned"
    assert payload["budget"]["usage"]["model_calls"] == 1
    assert payload["budget"]["limits"]["max_model_calls"] == 20
    assert payload["pending_approvals"] == []
    serialized = json.dumps(payload)
    assert "dev-litellm-key" not in serialized
    assert "refund_order" not in serialized
    assert "required_json_schema" not in serialized


def test_agent_execute_schema_failure_leaves_no_staged_outputs(tmp_path: Path) -> None:
    model_calls: list[dict[str, Any]] = []

    def invalid_transport(url: str, headers: dict[str, str], payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        model_calls.append({"url": url, "headers": headers, "payload": payload, "timeout": timeout_seconds})
        return {
            "id": "chatcmpl-invalid-agent-test",
            "model": payload["model"],
            "choices": [{"message": {"content": json.dumps({"case_candidates": [{"title": "Too thin"}]})}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 5},
        }

    client = make_client(tmp_path, invalid_transport)
    workspace, project = create_workspace_project(client)
    source = create_refund_fixture_repo(tmp_path)
    repository = bind_repository(client, workspace["id"], project["id"], source)
    repository = sync_repository(client, workspace["id"], project["id"], repository["id"])
    run = create_agent_run(client, workspace["id"], project["id"])

    response = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execute?actor_email={OWNER}",
        json={"repository_id": repository["id"], "ref": "master"},
    )

    assert response.status_code == 200, response.json()
    assert response.json()["run"]["status"] == "failed"
    assert response.json()["staged_outputs"] == []
    coverage = client.get(f"/api/workspaces/{workspace['id']}/projects/{project['id']}/coverage-index").json()
    assert coverage == []
    invocations = client.get(f"/api/workspaces/{workspace['id']}/ai-invocations").json()
    assert invocations[0]["status"] == "succeeded"
    assert invocations[0]["agent_run_id"] == run["id"]


def test_agent_execute_rejects_preview_mode_write(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    workspace, project = create_workspace_project(client)
    source = create_refund_fixture_repo(tmp_path)
    repository = bind_repository(client, workspace["id"], project["id"], source)
    run = create_agent_run(client, workspace["id"], project["id"], mode="preview")

    response = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execute?actor_email={OWNER}",
        json={"repository_id": repository["id"], "ref": "master"},
    )

    assert response.status_code == 409
    assert "execute mode" in response.json()["detail"]


def test_model_gateway_via_litellm_mock(tmp_path: Path) -> None:
    model_calls: list[dict[str, Any]] = []

    def flaky_transport(url: str, headers: dict[str, str], payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        model_calls.append({"url": url, "headers": headers, "payload": payload, "timeout": timeout_seconds})
        if len(model_calls) < 3:
            raise RetryableModelGatewayError("temporary litellm failure")
        return {
            "id": "chatcmpl-agent-test",
            "model": payload["model"],
            "choices": [{"message": {"content": case_candidate_content()}}],
        }

    client = make_client(tmp_path, flaky_transport)
    workspace, project = create_workspace_project(client)
    source = create_refund_fixture_repo(tmp_path)
    repository = bind_repository(client, workspace["id"], project["id"], source)
    repository = sync_repository(client, workspace["id"], project["id"], repository["id"])
    run = create_agent_run(client, workspace["id"], project["id"])

    response = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execute?actor_email={OWNER}",
        json={"repository_id": repository["id"], "ref": "master"},
    )

    assert response.status_code == 200, response.json()
    assert response.json()["run"]["status"] == "succeeded"
    assert len(model_calls) == 3
    assert {call["payload"]["model"] for call in model_calls} == {"qf-supervisor-strong"}
    invocations = client.get(f"/api/workspaces/{workspace['id']}/ai-invocations").json()
    assert invocations[0]["attempts"] == 3
    assert invocations[0]["status"] == "succeeded"


def test_agent_tool_calls_and_approvals_are_audited() -> None:
    client = make_client()
    workspace, project = create_workspace_project(client)
    conversation = client.post(
        f"/api/workspaces/{workspace['id']}/agent/conversations?actor_email={OWNER}",
        json={"title": "Tool audit", "project_id": project["id"]},
    ).json()
    run = client.post(
        f"/api/workspaces/{workspace['id']}/agent/conversations/{conversation['id']}/runs?actor_email={OWNER}",
        json={"goal": "Read code and request approval", "mode": "execute"},
    ).json()

    tool_call_response = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/tool-calls?actor_email={OWNER}",
        json={
            "tool_name": "code_search",
            "permission_level": "read",
            "input_summary": "Search refund audit keywords under checkout module",
            "output_summary": "Found refund.created audit signal",
            "status": "succeeded",
            "subagent_name": "CodeAnalysisSubAgent",
            "duration_ms": 42,
            "idempotency_key": "run-code-search-refund",
        },
    )
    assert tool_call_response.status_code == 201
    tool_call = tool_call_response.json()
    assert tool_call["tool_name"] == "code_search"
    assert tool_call["permission_level"] == "read"
    assert tool_call["completed_at"] is not None

    listed_tool_calls = client.get(f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/tool-calls").json()
    assert [item["id"] for item in listed_tool_calls] == [tool_call["id"]]

    approval_response = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/approvals?actor_email={OWNER}",
        json={"approval_type": "bulk_accept_staged_outputs", "request_summary": "Accept 12 generated case candidates"},
    )
    assert approval_response.status_code == 201
    approval = approval_response.json()
    assert approval["status"] == "pending"

    decided_response = client.patch(
        f"/api/workspaces/{workspace['id']}/agent/approvals/{approval['id']}?actor_email={OWNER}",
        json={"status": "approved", "decision_summary": "Batch is scoped to checkout refund only"},
    )
    assert decided_response.status_code == 200
    decided = decided_response.json()
    assert decided["status"] == "approved"
    assert decided["decided_by"] == OWNER
    assert decided["decided_at"] is not None

    second_decision = client.patch(
        f"/api/workspaces/{workspace['id']}/agent/approvals/{approval['id']}?actor_email={OWNER}",
        json={"status": "rejected"},
    )
    assert second_decision.status_code == 409

    audit_logs = client.get(f"/api/workspaces/{workspace['id']}/audit-logs").json()
    actions = [entry["action"] for entry in audit_logs]
    assert "agent_tool_call.recorded" in actions
    assert "agent_approval.requested" in actions
    assert "agent_approval.approved" in actions
