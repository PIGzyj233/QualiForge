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
            "name": "AI Lab",
            "owner_email": "owner@qualiforge.local",
            "owner_display_name": "Workspace Owner",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_provider(client: TestClient, workspace_id: str, api_base_url: str = "https://api.openai.example/v1") -> dict:
    response = client.post(
        f"/api/workspaces/{workspace_id}/llm-providers?actor_email=owner@qualiforge.local",
        json={
            "name": "OpenAI Compatible",
            "api_base_url": api_base_url,
            "api_key": "sk-test-secret",
            "default_headers": {"X-Team": "qa"},
            "organization": "qualiforge",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_profile(client: TestClient, workspace_id: str, provider_id: str, purpose: str = "import_cleanup") -> dict:
    response = client.post(
        f"/api/workspaces/{workspace_id}/model-profiles?actor_email=owner@qualiforge.local",
        json={
            "provider_id": provider_id,
            "purpose": purpose,
            "model_name": "gpt-test",
            "reasoning_effort": "medium",
            "max_context_tokens": 128000,
            "max_output_tokens": 4096,
            "input_token_price": "2.00",
            "output_token_price": "8.00",
            "cache_policy": "semantic",
            "timeout_seconds": 90,
            "retry_count": 2,
            "budget_limit": "25.00",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_provider_masks_api_key_and_records_audit() -> None:
    client = make_client()
    workspace = create_workspace(client)

    provider = create_provider(client, workspace["id"])

    assert provider["api_key_masked"] == "sk-t...cret"
    assert provider["has_api_key"] is True
    assert provider["default_headers"] == {"X-Team": "qa"}
    assert "api_key" not in provider
    audit_logs = client.get(f"/api/workspaces/{workspace['id']}/audit-logs").json()
    assert "llm_provider.created" in [entry["action"] for entry in audit_logs]
    assert "sk-test-secret" not in str(audit_logs)


def test_model_profiles_are_configured_per_purpose() -> None:
    client = make_client()
    workspace = create_workspace(client)
    provider = create_provider(client, workspace["id"])

    profile = create_profile(client, workspace["id"], provider["id"], "diff_analysis")

    assert profile["purpose"] == "diff_analysis"
    assert profile["model_name"] == "gpt-test"
    profiles = client.get(f"/api/workspaces/{workspace['id']}/model-profiles").json()
    assert [item["purpose"] for item in profiles] == ["diff_analysis"]


def test_ai_data_policy_blocks_source_code_and_logs_rejection_without_prompt() -> None:
    client = make_client()
    workspace = create_workspace(client)
    provider = create_provider(client, workspace["id"])
    create_profile(client, workspace["id"], provider["id"], "diff_analysis")
    policy = client.put(
        f"/api/workspaces/{workspace['id']}/ai-settings?actor_email=owner@qualiforge.local",
        json={"data_policy": "NoSourceCode"},
    )
    assert policy.status_code == 200

    rejected = client.post(
        f"/api/workspaces/{workspace['id']}/ai-invocations?actor_email=owner@qualiforge.local",
        json={
            "purpose": "diff_analysis",
            "input_summary": "Analyze tag diff for checkout service",
            "input_data_types": ["diff", "source_code"],
            "includes_source_code": True,
            "prompt": "this must not be stored",
        },
    )

    assert rejected.status_code == 403
    invocations = client.get(f"/api/workspaces/{workspace['id']}/ai-invocations").json()
    assert invocations[0]["status"] == "rejected"
    assert invocations[0]["failure_reason"] == "Workspace policy forbids sending source code to AI providers"
    assert "this must not be stored" not in str(invocations)


def test_ai_invocation_records_tokens_cost_cache_latency_and_failure() -> None:
    client = make_client()
    workspace = create_workspace(client)
    provider = create_provider(client, workspace["id"])
    create_profile(client, workspace["id"], provider["id"], "report_summary")

    started = client.post(
        f"/api/workspaces/{workspace['id']}/ai-invocations?actor_email=owner@qualiforge.local",
        json={
            "purpose": "report_summary",
            "input_summary": "Draft release report from execution facts",
            "input_data_types": ["test_plan", "execution_stats"],
            "includes_source_code": False,
        },
    )
    assert started.status_code == 201
    invocation_id = started.json()["id"]

    completed = client.patch(
        f"/api/workspaces/{workspace['id']}/ai-invocations/{invocation_id}?actor_email=owner@qualiforge.local",
        json={
            "status": "failed",
            "token_prompt": 1000,
            "token_completion": 500,
            "cache_hit": True,
            "latency_ms": 1234,
            "failure_reason": "provider timeout",
        },
    )

    assert completed.status_code == 200
    payload = completed.json()
    assert payload["status"] == "failed"
    assert payload["token_prompt"] == 1000
    assert payload["token_completion"] == 500
    assert payload["estimated_cost"] == "0.006000"
    assert payload["cache_hit"] is True
    assert payload["latency_ms"] == 1234
    assert payload["failure_reason"] == "provider timeout"


def test_internal_only_rejects_external_provider() -> None:
    client = make_client()
    workspace = create_workspace(client)
    provider = create_provider(client, workspace["id"], "https://api.external.example/v1")
    create_profile(client, workspace["id"], provider["id"], "case_generation")
    client.put(
        f"/api/workspaces/{workspace['id']}/ai-settings?actor_email=owner@qualiforge.local",
        json={"data_policy": "InternalOnly"},
    )

    response = client.post(
        f"/api/workspaces/{workspace['id']}/ai-invocations?actor_email=owner@qualiforge.local",
        json={
            "purpose": "case_generation",
            "input_summary": "Generate candidate cases",
            "input_data_types": ["diff_summary"],
            "includes_source_code": False,
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Workspace policy allows only internal model endpoints"

