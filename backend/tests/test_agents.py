from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agents import AgentRun, AgentRunStatus, AgentStagedOutput, CoverageIndexEntry
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
        "agent_memory_root": str(tmp_path / "agent-memory") if tmp_path else ".qualiforge/test-agent-memory",
        "model_gateway_provider": "deepseek",
        "model_gateway_api_base_url": "http://model-endpoint:4000/v1",
        "model_gateway_api_key": "test-model-key",
        "model_gateway_default_model": "deepseek-v4-pro",
        "model_gateway_reasoning_effort": "high",
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
    goal: str = "Generate refund audit candidate cases with observability",
    budget_snapshot: dict[str, Any] | None = None,
) -> dict:
    conversation = client.post(
        f"/api/workspaces/{workspace_id}/agent/conversations?actor_email={OWNER}",
        json={"title": "Generate refund cases", "project_id": project_id},
    ).json()
    run_response = client.post(
        f"/api/workspaces/{workspace_id}/agent/conversations/{conversation['id']}/runs?actor_email={OWNER}",
        json={
            "goal": goal,
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

    audit_logs = client.get(f"/api/workspaces/{workspace['id']}/audit-logs?actor_email={OWNER}").json()
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
    assert model_calls[0]["url"] == "http://model-endpoint:4000/v1/chat/completions"
    assert model_calls[0]["payload"]["model"] == "deepseek-v4-pro"
    assert model_calls[0]["payload"]["reasoning_effort"] == "high"
    assert "test-model-key" not in str(payload)

    invocations = client.get(f"/api/workspaces/{workspace['id']}/ai-invocations").json()
    assert invocations[0]["agent_run_id"] == run["id"]
    assert invocations[0]["provider_name"] == "deepseek"
    assert invocations[0]["model_alias"] == "deepseek-v4-pro"
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
    assert staged["quality_result"]["critic_result"]["critic"] == "CriticSubAgent"
    assert staged["quality_result"]["critic_result"]["passed"] is True
    assert staged["quality_result"]["critic_result"]["hallucination_risk"] == "low"
    assert staged["evidence_refs"][0]["kind"] == "code_file"
    assert staged["coverage_entries"][0]["coverage_state"] == "staged"
    assert staged["coverage_entries"][0]["module_key"] == "CHECKOUT"

    coverage = client.get(
        f"/api/workspaces/{workspace['id']}/projects/{project['id']}/coverage-index?coverage_state=staged&module_key=CHECKOUT"
    ).json()
    assert [entry["behavior_summary"] for entry in coverage] == ["Refund emits attributable audit and log signals."]


def test_critic_rejects_low_confidence_evidence_candidate(tmp_path: Path) -> None:
    model_calls: list[dict[str, Any]] = []

    def weak_evidence_transport(url: str, headers: dict[str, str], payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        model_calls.append({"url": url, "headers": headers, "payload": payload, "timeout": timeout_seconds})
        content = json.loads(case_candidate_content())
        content["case_candidates"][0]["evidence_refs"][0]["confidence"] = 0.1
        return {
            "id": "chatcmpl-weak-evidence-agent-test",
            "model": payload["model"],
            "choices": [{"message": {"content": json.dumps(content)}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 80},
        }

    client = make_client(tmp_path, weak_evidence_transport)
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
    assert payload["run"]["status"] == "failed"
    assert "Critic rejected all candidate" in payload["summary"]
    assert payload["staged_outputs"] == []
    assert model_calls


def test_agent_prometheus_metrics_cover_operational_paths(tmp_path: Path) -> None:
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
    output_id = executed.json()["staged_outputs"][0]["id"]
    accepted = client.patch(
        f"/api/workspaces/{workspace['id']}/agent/staged-outputs/{output_id}?actor_email={OWNER}",
        json={"status": "accepted", "decision_summary": "Looks good"},
    )
    approval = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/approvals?actor_email={OWNER}",
        json={"approval_type": "destructive_action", "request_summary": "Approve a gated operation"},
    )
    approved = client.patch(
        f"/api/workspaces/{workspace['id']}/agent/approvals/{approval.json()['id']}?actor_email={OWNER}",
        json={"status": "approved", "decision_summary": "Approved for metrics test"},
    )
    metrics = client.get("/api/metrics").text

    assert executed.status_code == 200, executed.json()
    assert accepted.status_code == 200, accepted.json()
    assert approval.status_code == 201, approval.json()
    assert approved.status_code == 200, approved.json()
    assert "qualiforge_agent_run_queue_time_seconds_count" in metrics
    assert "qualiforge_agent_tool_duration_seconds_count" in metrics
    assert 'qualiforge_agent_model_tokens_total{model="deepseek-v4-pro",token_type="prompt"}' in metrics
    assert 'qualiforge_agent_model_latency_seconds_count{model="deepseek-v4-pro",status="succeeded"}' in metrics
    assert 'qualiforge_agent_staged_output_decisions_total{output_type="case_candidate",status="accepted"}' in metrics
    assert 'qualiforge_agent_approval_wait_seconds_count{approval_type="destructive_action",status="approved"}' in metrics


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


def test_agent_run_budget_policy_applies_workspace_project_defaults_and_hard_caps(tmp_path: Path) -> None:
    client = make_client(
        tmp_path,
        settings_overrides={
            "agent_system_max_tool_calls": 50,
            "agent_system_max_parallel_subagents": 6,
        },
    )
    workspace, project = create_workspace_project(client)

    workspace_policy = client.put(
        f"/api/workspaces/{workspace['id']}/agent/budget-policies?actor_email={OWNER}",
        json={
            "scope": "workspace",
            "defaults": {"max_tool_calls": 30, "max_subagents": 3},
            "hard_caps": {"max_tool_calls": 45},
        },
    )
    project_policy = client.put(
        f"/api/workspaces/{workspace['id']}/agent/budget-policies?actor_email={OWNER}",
        json={
            "scope": "project",
            "project_id": project["id"],
            "defaults": {"max_tool_calls": 44, "max_model_calls": 7},
            "hard_caps": {"max_tool_calls": 40},
        },
    )
    run = create_agent_run(
        client,
        workspace["id"],
        project["id"],
        budget_snapshot={"max_tool_calls": 99, "max_parallel_subagents": 99},
    )

    assert workspace_policy.status_code == 200, workspace_policy.json()
    assert project_policy.status_code == 200, project_policy.json()
    snapshot = run["budget_snapshot"]
    assert snapshot["max_tool_calls"] == 40
    assert snapshot["max_model_calls"] == 7
    assert snapshot["max_subagents"] == 3
    assert snapshot["max_parallel_subagents"] == 6
    assert snapshot["system_hard_caps"]["max_tool_calls"] == 40
    assert [source["scope"] for source in snapshot["budget_sources"]] == [
        "system_defaults",
        "workspace",
        "project",
        "run_override",
    ]


def test_agent_execute_waits_when_subagent_budget_exceeded(tmp_path: Path) -> None:
    model_calls: list[dict[str, Any]] = []
    client = make_client(tmp_path, successful_model_transport(model_calls))
    workspace, project = create_workspace_project(client)
    source = create_refund_fixture_repo(tmp_path)
    repository = bind_repository(client, workspace["id"], project["id"], source)
    repository = sync_repository(client, workspace["id"], project["id"], repository["id"])
    run = create_agent_run(client, workspace["id"], project["id"], budget_snapshot={"max_subagents": 2})

    response = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execute?actor_email={OWNER}",
        json={"repository_id": repository["id"], "ref": "master"},
    )

    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload["run"]["status"] == "waiting_for_user"
    assert "subagent budget exceeded" in payload["run"]["failure_reason"]
    assert payload["staged_outputs"] == []
    assert model_calls == []


def test_agent_subagent_plan_honors_dynamic_disables_and_skips_unknown_requests(tmp_path: Path) -> None:
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
        budget_snapshot={
            "disable_critic": True,
            "disabled_subagents": ["RegressionScopeSubAgent"],
            "requested_subagents": ["UnknownSubAgent", "RegressionScopeSubAgent"],
        },
    )

    executed = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execute?actor_email={OWNER}",
        json={"repository_id": repository["id"], "ref": "master"},
    )
    detail = client.get(f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execution-detail")

    assert executed.status_code == 200, executed.json()
    assert detail.status_code == 200, detail.json()
    payload = detail.json()
    plan = payload["budget"]["snapshot"]["subagent_plan"]
    assert plan["selection_policy"] == "registry_dynamic_v1"
    assert plan["selected"] == ["CodeAnalysisSubAgent", "CaseDesignSubAgent"]
    assert {item["name"]: item["reason"] for item in plan["skipped_subagents"]} == {
        "UnknownSubAgent": "unknown_subagent",
        "RegressionScopeSubAgent": "disabled",
        "CriticSubAgent": "disabled",
    }
    assert payload["budget"]["usage"]["subagents"] == 2
    assert payload["budget"]["usage"]["parallel_subagents"] == 1
    assert "RegressionScopeSubAgent" not in {item["subagent_name"] for item in payload["tool_calls"]}
    assert "CriticSubAgent" not in plan["selected"]
    subagent_runs = {item["subagent_name"]: item for item in payload["subagent_runs"]}
    assert subagent_runs["CodeAnalysisSubAgent"]["status"] == "succeeded"
    assert subagent_runs["CaseDesignSubAgent"]["status"] == "succeeded"
    assert subagent_runs["RegressionScopeSubAgent"]["status"] == "skipped"
    assert subagent_runs["CriticSubAgent"]["status"] == "skipped"
    assert subagent_runs["UnknownSubAgent"]["status"] == "skipped"


def test_agent_subagent_plan_can_request_import_and_report_subagents(tmp_path: Path) -> None:
    from app.case_imports import ImportBatch, ImportBatchStatus, ImportCaseDraft

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
        goal="Import historical refund cases and draft release report candidates",
        budget_snapshot={
            "max_subagents": 6,
            "max_parallel_subagents": 3,
            "requested_subagents": ["ImportAnalysisSubAgent", "ReportDraftSubAgent"],
        },
    )
    with client.app.state.database.session_factory() as db:
        batch = ImportBatch(
            workspace_id=workspace["id"],
            project_id=project["id"],
            file_name="legacy-refund-cases.csv",
            file_type="csv",
            original_file_path=str(tmp_path / "legacy-refund-cases.csv"),
            status=ImportBatchStatus.preview_ready.value,
            created_by=OWNER,
            row_count=2,
            raw_rows=[{"title": "Refund imported case"}, {"title": "Refund imported gap"}],
        )
        db.add(batch)
        db.flush()
        db.add_all(
            [
                ImportCaseDraft(
                    workspace_id=workspace["id"],
                    project_id=project["id"],
                    batch_id=batch.id,
                    module_id="module-checkout",
                    title="Refund imported case",
                    steps=[
                        {"action": "Create order", "expected": ""},
                        {"action": "Refund order", "expected": "refund.created audit event is recorded"},
                    ],
                    expected_result="",
                    priority="P1",
                    risk="high",
                    source_row_index=1,
                    raw_row={"title": "Refund imported case"},
                    ai_confidence=92,
                ),
                ImportCaseDraft(
                    workspace_id=workspace["id"],
                    project_id=project["id"],
                    batch_id=batch.id,
                    module_id=None,
                    title="Refund imported gap",
                    steps=[],
                    expected_result="",
                    priority="P2",
                    risk="medium",
                    source_row_index=2,
                    raw_row={"title": "Refund imported gap"},
                    ai_confidence=70,
                ),
            ]
        )
        db.commit()

    executed = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execute?actor_email={OWNER}",
        json={"repository_id": repository["id"], "ref": "master"},
    )
    detail = client.get(f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execution-detail")

    assert executed.status_code == 200, executed.json()
    assert detail.status_code == 200, detail.json()
    payload = detail.json()
    plan = payload["budget"]["snapshot"]["subagent_plan"]
    assert {
        "CodeAnalysisSubAgent",
        "ImportAnalysisSubAgent",
        "RegressionScopeSubAgent",
        "CaseDesignSubAgent",
        "CriticSubAgent",
        "ReportDraftSubAgent",
    } <= set(plan["selected"])
    assert plan["parallel_groups"][0] == [
        "CodeAnalysisSubAgent",
        "ImportAnalysisSubAgent",
        "RegressionScopeSubAgent",
    ]
    assert plan["parallel_groups"][-1] == ["ReportDraftSubAgent"]
    assert payload["budget"]["usage"]["subagents"] == 6
    assert payload["budget"]["usage"]["parallel_subagents"] == 3
    available = {item["name"]: item for item in plan["available_subagents"]}
    assert available["ImportAnalysisSubAgent"]["stage"] == "import_analysis"
    assert available["ReportDraftSubAgent"]["stage"] == "report_draft"
    import_result = payload["budget"]["snapshot"]["subagent_results"]["ImportAnalysisSubAgent"]
    assert import_result["source"] == "database"
    assert import_result["batch_count"] == 1
    assert import_result["draft_count"] == 2
    assert import_result["unmapped_draft_count"] == 1
    subagent_runs = {item["subagent_name"]: item for item in payload["subagent_runs"]}
    assert subagent_runs["ImportAnalysisSubAgent"]["status"] == "succeeded"
    assert subagent_runs["ImportAnalysisSubAgent"]["result_snapshot"]["draft_count"] == 2
    assert subagent_runs["ImportAnalysisSubAgent"]["result_snapshot"]["parallel_execution"] == "read_analysis_thread"
    assert "parallel group" in subagent_runs["ImportAnalysisSubAgent"]["output_summary"]
    assert subagent_runs["ReportDraftSubAgent"]["status"] == "succeeded"
    assert subagent_runs["ReportDraftSubAgent"]["stage"] == "report_draft"
    prompt_payload = model_calls[0]["payload"]["messages"][1]["content"]
    assert '"subagent_results"' in prompt_payload
    assert '"ImportAnalysisSubAgent"' in prompt_payload


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


def test_agent_execute_allows_internal_model_endpoint_under_internal_only(tmp_path: Path) -> None:
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
    assert model_calls[0]["url"] == "http://model-endpoint:4000/v1/chat/completions"
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
    assert "test-model-key" not in serialized_invocation
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
    audit_logs = client.get(f"/api/workspaces/{workspace['id']}/audit-logs?actor_email={OWNER}").json()
    actions = [entry["action"] for entry in audit_logs]
    assert "agent_run.budget_overridden" in actions


def test_agent_resume_budget_override_respects_project_hard_caps(tmp_path: Path) -> None:
    model_calls: list[dict[str, Any]] = []
    client = make_client(tmp_path, successful_model_transport(model_calls))
    workspace, project = create_workspace_project(client)
    policy = client.put(
        f"/api/workspaces/{workspace['id']}/agent/budget-policies?actor_email={OWNER}",
        json={
            "scope": "project",
            "project_id": project["id"],
            "defaults": {"max_model_calls": 0},
            "hard_caps": {"max_model_calls": 1},
        },
    )
    source = create_refund_fixture_repo(tmp_path)
    repository = bind_repository(client, workspace["id"], project["id"], source)
    repository = sync_repository(client, workspace["id"], project["id"], repository["id"])
    run = create_agent_run(client, workspace["id"], project["id"], budget_snapshot={"max_model_calls": 0})

    waiting = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execute?actor_email={OWNER}",
        json={"repository_id": repository["id"], "ref": "master"},
    )
    resumed = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/resume?actor_email={OWNER}",
        json={
            "budget_snapshot": {"max_model_calls": 99},
            "resume_reason": "Try to exceed project policy cap",
        },
    )

    assert policy.status_code == 200, policy.json()
    assert waiting.status_code == 200, waiting.json()
    assert waiting.json()["run"]["status"] == "waiting_for_user"
    assert resumed.status_code == 200, resumed.json()
    snapshot = resumed.json()["run"]["budget_snapshot"]
    assert resumed.json()["run"]["status"] == "succeeded"
    assert snapshot["max_model_calls"] == 1
    assert snapshot["limits"]["max_model_calls"] == 1
    assert snapshot["system_hard_caps"]["max_model_calls"] == 1
    assert snapshot["budget_sources"][-1] == {"scope": "resume_override", "keys": ["max_model_calls"]}
    assert len(model_calls) == 1


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


def test_temporal_execute_starts_workflow_and_returns_accepted(tmp_path: Path) -> None:
    client = make_client(tmp_path, settings_overrides={"agent_execute_sync_mode": False})
    workspace, project = create_workspace_project(client)
    source = create_refund_fixture_repo(tmp_path)
    repository = bind_repository(client, workspace["id"], project["id"], source)
    repository = sync_repository(client, workspace["id"], project["id"], repository["id"])
    run = create_agent_run(client, workspace["id"], project["id"])
    started: list[dict[str, Any]] = []

    def workflow_starter(**kwargs):
        stored_run = kwargs["run"]
        stored_run.temporal_workflow_id = f"agent-run-{stored_run.id}"
        stored_run.current_phase = "temporal_queued"
        kwargs["db"].commit()
        started.append(kwargs)
        return {"summary": "Agent workflow started"}

    client.app.state.agent_workflow_starter = workflow_starter

    response = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execute?actor_email={OWNER}",
        json={"repository_id": repository["id"], "ref": "master", "candidate_limit": 3},
    )

    assert response.status_code == 202, response.json()
    payload = response.json()
    assert payload["run"]["temporal_workflow_id"] == f"agent-run-{run['id']}"
    assert payload["run"]["current_phase"] == "temporal_queued"
    assert payload["staged_outputs"] == []
    assert started[0]["repository_id"] == repository["id"]


def test_temporal_workflow_starter_includes_budget_child_tasks(tmp_path: Path, monkeypatch) -> None:
    import app.agent_temporal as agent_temporal

    client = make_client(tmp_path, settings_overrides={"agent_execute_sync_mode": False})
    workspace, project = create_workspace_project(client)
    source = create_refund_fixture_repo(tmp_path)
    repository = bind_repository(client, workspace["id"], project["id"], source)
    repository = sync_repository(client, workspace["id"], project["id"], repository["id"])
    run = create_agent_run(
        client,
        workspace["id"],
        project["id"],
        budget_snapshot={
            "child_tasks": [
                {"task_kind": "large_repo_scan", "summary": "Scan repository routes", "payload": {"path": "backend"}},
                "ignore-me",
                {"task_kind": "large_import_analysis", "summary": "Analyze imported rows"},
            ],
        },
    )
    captured: dict[str, Any] = {}

    class FakeTemporalClient:
        async def start_workflow(self, workflow, payload, **kwargs):
            captured["workflow"] = workflow
            captured["payload"] = payload
            captured["kwargs"] = kwargs

    async def fake_connect(_settings):
        return FakeTemporalClient()

    monkeypatch.setattr(agent_temporal, "_connect", fake_connect)
    with client.app.state.database.session_factory() as db:
        stored_run = db.get(AgentRun, run["id"])
        assert stored_run is not None
        result = agent_temporal.start_agent_run_workflow(
            db=db,
            settings=client.app.state.settings,
            run=stored_run,
            workspace_id=workspace["id"],
            repository_id=repository["id"],
            ref="master",
            candidate_limit=3,
            actor_email=OWNER,
        )

    assert result["workflow_id"] == f"agent-run-{run['id']}"
    assert captured["payload"]["child_tasks"] == [
        {"task_kind": "large_repo_scan", "summary": "Scan repository routes", "payload": {"path": "backend"}},
        {"task_kind": "large_import_analysis", "summary": "Analyze imported rows", "payload": {}},
    ]
    assert captured["kwargs"]["id"] == f"agent-run-{run['id']}"
    audit_logs = client.get(f"/api/workspaces/{workspace['id']}/audit-logs?actor_email={OWNER}").json()
    started = [entry for entry in audit_logs if entry["action"] == "agent_run.workflow_started"]
    assert started[-1]["after"]["child_task_count"] == 2


def test_agent_child_task_activity_scans_synced_repository(tmp_path: Path) -> None:
    from app.agent_activities import execute_agent_child_task_activity_with_settings

    client = make_client(tmp_path, settings_overrides={"database_url": f"sqlite+pysqlite:///{tmp_path / 'child-scan.db'}"})
    workspace, project = create_workspace_project(client)
    source = create_refund_fixture_repo(tmp_path)
    repository = bind_repository(client, workspace["id"], project["id"], source)
    repository = sync_repository(client, workspace["id"], project["id"], repository["id"])
    run = create_agent_run(client, workspace["id"], project["id"])

    result = execute_agent_child_task_activity_with_settings(
        {
            "workspace_id": workspace["id"],
            "parent_run_id": run["id"],
            "repository_id": repository["id"],
            "ref": "master",
            "task_kind": "large_repo_scan",
            "payload": {"timeout_seconds": 10},
        },
        settings=client.app.state.settings,
    )

    assert result["status"] == "succeeded"
    assert result["task_kind"] == "large_repo_scan"
    assert result["parent_run_id"] == run["id"]
    assert result["file_count"] >= 1
    assert result["resolved_ref"]
    assert any(item["extension"] == ".py" for item in result["top_extensions"])
    assert "Scanned" in result["summary"]


def test_agent_child_task_activity_analyzes_import_batches(tmp_path: Path) -> None:
    from app.agent_activities import execute_agent_child_task_activity_with_settings
    from app.case_imports import ImportBatch, ImportBatchStatus, ImportCaseDraft

    client = make_client(tmp_path, settings_overrides={"database_url": f"sqlite+pysqlite:///{tmp_path / 'child-import.db'}"})
    workspace, project = create_workspace_project(client)
    run = create_agent_run(client, workspace["id"], project["id"])
    with client.app.state.database.session_factory() as db:
        batch = ImportBatch(
            workspace_id=workspace["id"],
            project_id=project["id"],
            file_name="legacy-refund-cases.csv",
            file_type="csv",
            original_file_path=str(tmp_path / "legacy-refund-cases.csv"),
            status=ImportBatchStatus.preview_ready.value,
            created_by=OWNER,
            row_count=2,
            raw_rows=[{"title": "Refund happy path"}, {"title": "Refund audit missing steps"}],
        )
        db.add(batch)
        db.flush()
        db.add_all(
            [
                ImportCaseDraft(
                    workspace_id=workspace["id"],
                    project_id=project["id"],
                    batch_id=batch.id,
                    module_id="module-checkout",
                    title="Refund happy path",
                    steps=["Create order", "Refund order"],
                    expected_result="refund.created audit event is recorded",
                    priority="P1",
                    risk="high",
                    source_row_index=1,
                    raw_row={"title": "Refund happy path"},
                    ai_confidence=92,
                ),
                ImportCaseDraft(
                    workspace_id=workspace["id"],
                    project_id=project["id"],
                    batch_id=batch.id,
                    module_id=None,
                    title="Refund audit missing steps",
                    steps=[],
                    expected_result="",
                    priority="P2",
                    risk="medium",
                    source_row_index=2,
                    raw_row={"title": "Refund audit missing steps"},
                    ai_confidence=70,
                ),
            ]
        )
        db.commit()

    result = execute_agent_child_task_activity_with_settings(
        {
            "workspace_id": workspace["id"],
            "project_id": project["id"],
            "parent_run_id": run["id"],
            "task_kind": "large_import_analysis",
        },
        settings=client.app.state.settings,
    )

    assert result["status"] == "succeeded"
    assert result["task_kind"] == "large_import_analysis"
    assert result["batch_count"] == 1
    assert result["row_count"] == 2
    assert result["draft_count"] == 2
    assert result["unmapped_draft_count"] == 1
    assert result["missing_steps_count"] == 1
    assert result["missing_expected_result_count"] == 1
    assert result["risk_counts"] == {"high": 1, "medium": 1}
    assert result["priority_counts"] == {"P1": 1, "P2": 1}
    assert result["average_ai_confidence"] == 81.0


def test_temporal_unavailable_returns_clear_error_without_staged_outputs(tmp_path: Path) -> None:
    from app.agent_temporal import AgentTemporalUnavailable

    client = make_client(tmp_path, settings_overrides={"agent_execute_sync_mode": False})
    workspace, project = create_workspace_project(client)
    run = create_agent_run(client, workspace["id"], project["id"])

    def workflow_starter(**_kwargs):
        raise AgentTemporalUnavailable("Temporal unavailable: test")

    client.app.state.agent_workflow_starter = workflow_starter

    response = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execute?actor_email={OWNER}",
        json={"repository_id": "missing", "ref": "master", "candidate_limit": 3},
    )
    detail = client.get(f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execution-detail")

    assert response.status_code == 503
    assert "Temporal unavailable" in response.json()["detail"]
    assert detail.json()["staged_outputs"] == []


def test_temporal_cancel_marks_run_cancelled_and_invokes_workflow_cancel(tmp_path: Path) -> None:
    client = make_client(tmp_path, settings_overrides={"agent_execute_sync_mode": False})
    workspace, project = create_workspace_project(client)
    run = create_agent_run(client, workspace["id"], project["id"])
    with client.app.state.database.session_factory() as db:
        stored = db.get(AgentRun, run["id"])
        assert stored is not None
        stored.status = AgentRunStatus.running.value
        stored.current_phase = "generate_candidates"
        stored.temporal_workflow_id = f"agent-run-{run['id']}"
        db.commit()
    cancelled_workflows: list[dict] = []

    def workflow_canceller(**kwargs):
        cancelled_workflows.append(dict(kwargs))

    client.app.state.agent_workflow_canceller = workflow_canceller

    response = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/cancel?actor_email={OWNER}",
        json={"cancel_reason": "Stop durable run"},
    )

    assert response.status_code == 200, response.json()
    assert response.json()["status"] == "cancelled"
    assert cancelled_workflows[0]["workflow_id"] == f"agent-run-{run['id']}"
    assert cancelled_workflows[0]["cancel_reason"] == "Stop durable run"
    assert cancelled_workflows[0]["actor_email"] == OWNER


def test_temporal_resume_sends_signal_with_budget_override(tmp_path: Path) -> None:
    client = make_client(tmp_path, settings_overrides={"agent_execute_sync_mode": False})
    workspace, project = create_workspace_project(client)
    run = create_agent_run(client, workspace["id"], project["id"], budget_snapshot={"max_model_calls": 0})
    with client.app.state.database.session_factory() as db:
        stored = db.get(AgentRun, run["id"])
        assert stored is not None
        stored.status = AgentRunStatus.waiting_for_user.value
        stored.current_phase = "budget_waiting"
        stored.failure_reason = "model budget exceeded"
        stored.temporal_workflow_id = f"agent-run-{run['id']}"
        db.commit()
    signalled: list[str] = []

    def resume_signaler(**kwargs):
        signalled.append(kwargs["run"].id)

    client.app.state.agent_workflow_resume_signaler = resume_signaler

    response = client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/resume?actor_email={OWNER}",
        json={"budget_snapshot": {"max_model_calls": 5}, "resume_reason": "Allow one model call"},
    )

    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload["summary"] == "Agent workflow resume signal sent"
    assert payload["run"]["budget_snapshot"]["max_model_calls"] == 5
    assert signalled == [run["id"]]


def test_temporal_failure_activity_marks_running_run_failed(tmp_path: Path) -> None:
    from app.agent_activities import mark_agent_run_failed_with_settings
    from app.workspaces import AuditLog

    client = make_client(tmp_path, settings_overrides={"database_url": f"sqlite+pysqlite:///{tmp_path / 'temporal-failure.db'}"})
    workspace, project = create_workspace_project(client)
    run = create_agent_run(client, workspace["id"], project["id"])
    with client.app.state.database.session_factory() as db:
        stored = db.get(AgentRun, run["id"])
        assert stored is not None
        stored.status = AgentRunStatus.running.value
        stored.current_phase = "generate_candidates"
        db.commit()

    result = mark_agent_run_failed_with_settings(
        {
            "workspace_id": workspace["id"],
            "run_id": run["id"],
            "actor_email": OWNER,
            "failure_reason": "Temporal activity failed after retries: TimeoutError",
            "phase": "temporal_failed",
        },
        settings=client.app.state.settings,
    )

    with client.app.state.database.session_factory() as db:
        stored = db.get(AgentRun, run["id"])
        audits = db.scalars(select(AuditLog).where(AuditLog.entity_id == run["id"], AuditLog.action == "agent_run.failed")).all()

    assert result["status"] == "failed"
    assert stored is not None
    assert stored.status == "failed"
    assert stored.current_phase == "temporal_failed"
    assert "TimeoutError" in stored.failure_reason
    assert audits


def test_temporal_failure_activity_does_not_overwrite_cancelled_run(tmp_path: Path) -> None:
    from app.agent_activities import mark_agent_run_failed_with_settings

    client = make_client(tmp_path, settings_overrides={"database_url": f"sqlite+pysqlite:///{tmp_path / 'temporal-cancel-race.db'}"})
    workspace, project = create_workspace_project(client)
    run = create_agent_run(client, workspace["id"], project["id"])
    with client.app.state.database.session_factory() as db:
        stored = db.get(AgentRun, run["id"])
        assert stored is not None
        stored.status = AgentRunStatus.cancelled.value
        stored.current_phase = "cancelled"
        stored.failure_reason = "User cancelled first"
        db.commit()

    result = mark_agent_run_failed_with_settings(
        {
            "workspace_id": workspace["id"],
            "run_id": run["id"],
            "actor_email": OWNER,
            "failure_reason": "Temporal activity failed after retries",
            "phase": "temporal_failed",
        },
        settings=client.app.state.settings,
    )

    with client.app.state.database.session_factory() as db:
        stored = db.get(AgentRun, run["id"])

    assert result["status"] == "cancelled"
    assert stored is not None
    assert stored.status == "cancelled"
    assert stored.current_phase == "cancelled"
    assert stored.failure_reason == "User cancelled first"


def test_temporal_child_results_persist_to_execution_detail_once(tmp_path: Path) -> None:
    from app.agent_activities import persist_temporal_child_results
    from app.workspaces import AuditLog

    client = make_client(tmp_path)
    workspace, project = create_workspace_project(client)
    run = create_agent_run(client, workspace["id"], project["id"])
    payload = {
        "child_results": [
            {
                "status": "succeeded",
                "task_kind": "large_repo_scan",
                "parent_run_id": run["id"],
                "workflow_id": f"agent-run-{run['id']}-child-0-large_repo_scan",
                "summary": "Scanned repository routes before main graph execution",
                "file_count": 42,
                "top_extensions": [{"extension": ".py", "count": 9}],
            },
            "ignore-me",
            {
                "status": "succeeded",
                "task_kind": "large_import_analysis",
                "parent_run_id": run["id"],
                "workflow_id": f"agent-run-{run['id']}-child-1-large_import_analysis",
                "summary": "Analyzed imported case rows before main graph execution",
                "batch_count": 1,
                "draft_count": 2,
                "unmapped_draft_count": 1,
            },
        ]
    }

    with client.app.state.database.session_factory() as db:
        stored = db.get(AgentRun, run["id"])
        assert stored is not None
        first = persist_temporal_child_results(
            db,
            run=stored,
            workspace_id=workspace["id"],
            actor_email=OWNER,
            payload=payload,
        )
        second = persist_temporal_child_results(
            db,
            run=stored,
            workspace_id=workspace["id"],
            actor_email=OWNER,
            payload=payload,
        )
        db.commit()
        audits = db.scalars(
            select(AuditLog).where(AuditLog.entity_id == run["id"], AuditLog.action == "agent_run.child_tasks_completed")
        ).all()

    detail = client.get(f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execution-detail")

    assert len(first) == 2
    assert second == first
    assert len(audits) == 1
    assert detail.status_code == 200, detail.json()
    child_results = detail.json()["budget"]["snapshot"]["temporal_child_results"]
    assert [item["task_kind"] for item in child_results] == ["large_repo_scan", "large_import_analysis"]
    assert all("workflow_id" in item for item in child_results)
    assert child_results[0]["metadata"]["file_count"] == 42
    assert child_results[1]["metadata"]["draft_count"] == 2


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
    assert {"CodeAnalysisSubAgent", "RegressionScopeSubAgent"} <= {item["subagent_name"] for item in payload["tool_calls"]}
    subagent_runs = {item["subagent_name"]: item for item in payload["subagent_runs"]}
    assert subagent_runs["CodeAnalysisSubAgent"]["status"] == "succeeded"
    assert subagent_runs["CodeAnalysisSubAgent"]["result_snapshot"]["files_scanned"] >= 1
    assert subagent_runs["RegressionScopeSubAgent"]["parallel_group"] == "CodeAnalysisSubAgent+RegressionScopeSubAgent"
    assert subagent_runs["CaseDesignSubAgent"]["result_snapshot"]["candidate_count"] == 1
    assert subagent_runs["CriticSubAgent"]["status"] == "succeeded"
    assert payload["ai_invocations"][0]["status"] == "succeeded"
    assert payload["repository_sandboxes"][0]["status"] == "cleaned"
    assert payload["budget"]["snapshot"]["subagent_plan"]["parallel_groups"][0] == [
        "CodeAnalysisSubAgent",
        "RegressionScopeSubAgent",
    ]
    assert payload["budget"]["usage"]["subagents"] == 4
    assert payload["budget"]["usage"]["parallel_subagents"] == 2
    assert payload["budget"]["usage"]["model_calls"] == 1
    assert payload["budget"]["limits"]["max_model_calls"] == 20
    assert payload["pending_approvals"] == []
    serialized = json.dumps(payload)
    assert "test-model-key" not in serialized
    assert "refund_order" not in serialized
    assert "required_json_schema" not in serialized


def test_agent_execution_detail_exposes_budget_limits_before_graph_starts(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    workspace, project = create_workspace_project(client)
    run = create_agent_run(
        client,
        workspace["id"],
        project["id"],
        budget_snapshot={
            "max_tool_calls": 17,
            "max_model_calls": 0,
            "max_subagents": 3,
            "max_parallel_subagents": 2,
            "max_wall_time_minutes": 5,
            "max_total_source_chars_sent": 12345,
        },
    )

    detail = client.get(f"/api/workspaces/{workspace['id']}/agent/runs/{run['id']}/execution-detail")

    assert detail.status_code == 200, detail.json()
    budget = detail.json()["budget"]
    assert budget["limits"]["max_tool_calls"] == 17
    assert budget["limits"]["max_model_calls"] == 0
    assert budget["limits"]["max_subagents"] == 3
    assert budget["limits"]["max_parallel_subagents"] == 2
    assert budget["limits"]["max_wall_time_minutes"] == 5
    assert budget["limits"]["max_total_source_chars_sent"] == 12345
    assert budget["usage"]["tool_calls"] == 0
    assert budget["usage"]["model_calls"] == 0


def test_successful_agent_run_writes_searchable_daily_memory(tmp_path: Path) -> None:
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
    files = client.get(
        f"/api/workspaces/{workspace['id']}/agent/memory/files?project_id={project['id']}&scope=daily_project"
    )
    search = client.get(
        f"/api/workspaces/{workspace['id']}/agent/memory/search?project_id={project['id']}&query=refund%20audit"
    )
    audit_logs = client.get(f"/api/workspaces/{workspace['id']}/audit-logs?actor_email={OWNER}").json()

    assert executed.status_code == 200, executed.json()
    assert files.status_code == 200, files.json()
    assert files.json()[0]["scope"] == "daily_project"
    assert search.status_code == 200, search.json()
    assert search.json()[0]["memory_file"]["id"] == files.json()[0]["id"]
    serialized_memory = json.dumps(search.json())
    assert "test-model-key" not in serialized_memory
    assert "required_json_schema" not in serialized_memory
    assert "agent_memory.appended" in [entry["action"] for entry in audit_logs]


def test_staged_output_writer_is_idempotent_for_activity_retry(tmp_path: Path) -> None:
    from app.agent_graph import AgentGraphExecutor

    client = make_client(tmp_path)
    workspace, project = create_workspace_project(client)
    run = create_agent_run(client, workspace["id"], project["id"])
    candidate = json.loads(case_candidate_content())["case_candidates"][0]
    state = {
        "workspace_id": workspace["id"],
        "run_id": run["id"],
        "repository_id": "repo-retry-test",
        "requested_ref": "master",
        "resolved_ref": "abc123def456",
        "verified_candidates": [candidate],
        "reuse_recommendations": [],
    }

    with client.app.state.database.session_factory() as db:
        stored = db.get(AgentRun, run["id"])
        assert stored is not None
        executor = AgentGraphExecutor(
            db=db,
            settings=client.app.state.settings,
            run=stored,
            actor_email=OWNER,
            candidate_limit=3,
            model_gateway_transport=None,
        )
        first = executor.write_staged_outputs(state)
        db.commit()
        second = executor.write_staged_outputs(state)
        db.commit()

        outputs = db.scalars(select(AgentStagedOutput).where(AgentStagedOutput.agent_run_id == run["id"])).all()
        coverage = db.scalars(
            select(CoverageIndexEntry).where(
                CoverageIndexEntry.source_type == "staged_output",
                CoverageIndexEntry.source_id == outputs[0].id,
            )
        ).all()

    assert first["staged_output_ids"] == second["staged_output_ids"]
    assert len(outputs) == 1
    assert outputs[0].idempotency_key
    assert len(coverage) == 1


def test_agent_memory_curator_search_versions_rollback_and_secret_rejection(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    workspace, project = create_workspace_project(client)

    created = client.post(
        f"/api/workspaces/{workspace['id']}/agent/memory/curate?actor_email={OWNER}",
        json={
            "scope": "project",
            "project_id": project["id"],
            "content": "# Project Memory\n\nRefund coverage should assert refund.created audit evidence.\n",
            "patch_summary": "Seed refund memory",
        },
    )
    updated = client.post(
        f"/api/workspaces/{workspace['id']}/agent/memory/curate?actor_email={OWNER}",
        json={
            "scope": "project",
            "project_id": project["id"],
            "content": "# Project Memory\n\nRefund coverage should assert refund.completed metric evidence.\n",
            "patch_summary": "Update refund memory",
        },
    )
    versions = client.get(f"/api/workspaces/{workspace['id']}/agent/memory/files/{created.json()['id']}/versions")
    rolled_back = client.post(
        f"/api/workspaces/{workspace['id']}/agent/memory/files/{created.json()['id']}/rollback?actor_email={OWNER}",
        json={"target_version": 1, "reason": "Restore audit evidence guidance"},
    )
    search = client.get(
        f"/api/workspaces/{workspace['id']}/agent/memory/search?project_id={project['id']}&query=refund.created"
    )
    rejected = client.post(
        f"/api/workspaces/{workspace['id']}/agent/memory/curate?actor_email={OWNER}",
        json={
            "scope": "project",
            "project_id": project["id"],
            "content": "api key test-model-key should never be stored",
        },
    )
    audit_logs = client.get(f"/api/workspaces/{workspace['id']}/audit-logs?actor_email={OWNER}").json()

    assert created.status_code == 200, created.json()
    assert updated.status_code == 200, updated.json()
    assert updated.json()["current_version"] == 2
    assert versions.status_code == 200, versions.json()
    assert [version["version"] for version in versions.json()] == [2, 1]
    assert rolled_back.status_code == 200, rolled_back.json()
    assert rolled_back.json()["current_version"] == 3
    assert search.status_code == 200, search.json()
    assert "refund.created" in search.json()[0]["snippet"]
    assert rejected.status_code == 422
    actions = [entry["action"] for entry in audit_logs]
    assert actions.count("agent_memory.curated") == 2
    assert "agent_memory.rolled_back" in actions


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


def test_model_gateway_retries_openai_compatible_mock(tmp_path: Path) -> None:
    model_calls: list[dict[str, Any]] = []

    def flaky_transport(url: str, headers: dict[str, str], payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        model_calls.append({"url": url, "headers": headers, "payload": payload, "timeout": timeout_seconds})
        if len(model_calls) < 3:
            raise RetryableModelGatewayError("temporary model gateway failure")
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
    assert {call["payload"]["model"] for call in model_calls} == {"deepseek-v4-pro"}
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

    audit_logs = client.get(f"/api/workspaces/{workspace['id']}/audit-logs?actor_email={OWNER}").json()
    actions = [entry["action"] for entry in audit_logs]
    assert "agent_tool_call.recorded" in actions
    assert "agent_approval.requested" in actions
    assert "agent_approval.approved" in actions
