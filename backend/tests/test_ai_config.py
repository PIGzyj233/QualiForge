from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from app.config import Settings
from app.database import Database
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


def test_database_init_upgrades_legacy_ai_invocation_log_schema(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'legacy.db'}"
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE ai_invocation_logs (
                    id VARCHAR(32) PRIMARY KEY,
                    workspace_id VARCHAR(32) NOT NULL,
                    provider_id VARCHAR(32),
                    model_profile_id VARCHAR(32),
                    actor_email VARCHAR(254) NOT NULL,
                    purpose VARCHAR(40) NOT NULL,
                    data_policy VARCHAR(32) NOT NULL,
                    status VARCHAR(32) NOT NULL DEFAULT 'queued',
                    input_summary VARCHAR(500) NOT NULL,
                    input_data_types JSON NOT NULL DEFAULT '[]',
                    includes_source_code BOOLEAN NOT NULL DEFAULT 0,
                    token_prompt INTEGER NOT NULL DEFAULT 0,
                    token_completion INTEGER NOT NULL DEFAULT 0,
                    estimated_cost NUMERIC(12, 6) NOT NULL DEFAULT 0,
                    cache_hit BOOLEAN NOT NULL DEFAULT 0,
                    latency_ms INTEGER NOT NULL DEFAULT 0,
                    failure_reason VARCHAR(500) NOT NULL DEFAULT '',
                    created_at DATETIME NOT NULL,
                    completed_at DATETIME
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO ai_invocation_logs (
                    id, workspace_id, actor_email, purpose, data_policy, status,
                    input_summary, input_data_types, includes_source_code, created_at
                )
                VALUES (
                    'legacy-invocation', 'workspace-1', 'owner@qualiforge.local',
                    'case_generation', 'InternalOnly', 'succeeded',
                    'legacy row', '[]', 0, '2026-05-24 00:00:00'
                )
                """
            )
        )

    database = Database(database_url)
    database.init()

    inspector = inspect(database.engine)
    columns = {column["name"] for column in inspector.get_columns("ai_invocation_logs")}
    assert {
        "agent_run_id",
        "tool_call_id",
        "provider_name",
        "model_alias",
        "model_name",
        "attempts",
        "usage",
        "raw_invocation_id",
    } <= columns
    indexes = {index["name"] for index in inspector.get_indexes("ai_invocation_logs")}
    assert "ix_ai_invocation_logs_agent_run_id" in indexes
    assert "ix_ai_invocation_logs_model_alias" in indexes

    with database.engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT provider_name, model_alias, model_name, attempts, usage, raw_invocation_id
                FROM ai_invocation_logs
                WHERE id = 'legacy-invocation'
                """
            )
        ).mappings().one()
    assert row["provider_name"] == ""
    assert row["model_alias"] == ""
    assert row["model_name"] == ""
    assert row["attempts"] == 0
    assert row["usage"] == "{}"
    assert row["raw_invocation_id"] == ""


def test_database_init_upgrades_legacy_test_case_schema(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'legacy-cases.db'}"
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE test_cases (
                    id VARCHAR(32) PRIMARY KEY,
                    workspace_id VARCHAR(32) NOT NULL,
                    project_id VARCHAR(32) NOT NULL,
                    module_id VARCHAR(32),
                    import_batch_id VARCHAR(32),
                    title VARCHAR(300) NOT NULL,
                    steps JSON NOT NULL DEFAULT '[]',
                    expected_result VARCHAR(2000) NOT NULL DEFAULT '',
                    priority VARCHAR(32) NOT NULL DEFAULT 'P2',
                    risk VARCHAR(80) NOT NULL DEFAULT 'medium',
                    tags JSON NOT NULL DEFAULT '[]',
                    custom_fields JSON NOT NULL DEFAULT '{}',
                    status VARCHAR(32) NOT NULL DEFAULT 'draft',
                    submitted_by VARCHAR(254) NOT NULL DEFAULT '',
                    approved_by VARCHAR(254) NOT NULL DEFAULT '',
                    current_revision_number INTEGER NOT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO test_cases (
                    id, workspace_id, project_id, module_id, import_batch_id,
                    title, steps, status, submitted_by, created_at, updated_at
                )
                VALUES
                    (
                        'case-approved', 'workspace-1', 'project-1', 'module-1', 'batch-1',
                        'Approved legacy case', '[]', 'approved', 'reviewer@qualiforge.local',
                        '2026-05-24 00:00:00', '2026-05-24 00:00:00'
                    ),
                    (
                        'case-archived', 'workspace-1', 'project-1', NULL, NULL,
                        'Archived legacy case', '[]', 'archived', '',
                        '2026-05-24 00:00:00', '2026-05-24 00:00:00'
                    )
                """
            )
        )

    database = Database(database_url)
    database.init()

    inspector = inspect(database.engine)
    columns = {column["name"] for column in inspector.get_columns("test_cases")}
    assert {
        "lifecycle_status",
        "current_revision_id",
        "current_module_id",
        "source_type",
        "source_ref",
        "created_by",
    } <= columns
    indexes = {index["name"] for index in inspector.get_indexes("test_cases")}
    assert "ix_test_cases_lifecycle_status" in indexes
    assert "ix_test_cases_current_module_id" in indexes

    with database.engine.connect() as connection:
        rows = {
            row["id"]: row
            for row in connection.execute(
                text(
                    """
                    SELECT id, lifecycle_status, current_module_id, source_type, source_ref, created_by
                    FROM test_cases
                    ORDER BY id
                    """
                )
            ).mappings()
        }

    assert rows["case-approved"]["lifecycle_status"] == "active"
    assert rows["case-approved"]["current_module_id"] == "module-1"
    assert rows["case-approved"]["source_type"] == "import"
    assert rows["case-approved"]["source_ref"] == "{}"
    assert rows["case-approved"]["created_by"] == "reviewer@qualiforge.local"
    assert rows["case-archived"]["lifecycle_status"] == "archived"
