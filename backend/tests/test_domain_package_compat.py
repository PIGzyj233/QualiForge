from __future__ import annotations

import importlib

from app.platform.config import Settings
from app.platform.database import Database
from app.main import create_app
from app.platform.database import Base


def test_domain_modules_expose_expected_public_objects() -> None:
    module_contracts = [
        ("app.platform.config", ["Settings"]),
        ("app.platform.database", ["Database", "Base"]),
        ("app.platform.telemetry", ["agent_span"]),
        ("app.git.gitlab", ["GitRepository", "ensure_safe_sandbox_path"]),
        ("app.git.code_tools", ["code_search", "CodeReadResult"]),
        ("app.cases.domain", ["TestCase", "CaseDraft"]),
        ("app.cases.imports", ["ImportBatch", "safe_filename"]),
        ("app.cases.reviews", ["WorkspaceReviewSettings", "build_case_response"]),
        ("app.cases.diff_analysis", ["DiffAnalysis", "run_analysis"]),
        ("app.cases.ai_suggestions", ["AISuggestion"]),
        ("app.ai.config", ["WorkspaceAISettings", "AIInvocationLog"]),
        ("app.ai.model_gateway", ["build_model_gateway"]),
        ("app.planning.test_plans", ["TestPlan", "PlanItem"]),
        ("app.planning.release_reports", ["ReleaseReport"]),
        ("app.workspace.routes", ["Workspace", "AuditLog"]),
        ("app.cases.modules", ["ProjectModule", "ModuleMappingRule"]),
        ("app.agents.graph", ["AgentGraphExecutor", "execute_agent_graph"]),
        ("app.agents.memory", ["list_memory_files"]),
        ("app.agents.temporal", ["AgentTemporalUnavailable"]),
        ("app.agents.workflows", ["AgentRunWorkflow"]),
        ("app.agents.activities", ["mark_agent_run_failed_with_settings"]),
    ]

    for module_name, attributes in module_contracts:
        module = importlib.import_module(module_name)
        for attribute in attributes:
            assert getattr(module, attribute)


def test_agents_package_reexports_core_domain_objects() -> None:
    agents = importlib.import_module("app.agents")
    models = importlib.import_module("app.agents.models")
    schemas = importlib.import_module("app.agents.schemas")
    state = importlib.import_module("app.agents.state")

    assert agents.AgentRun is models.AgentRun
    assert agents.AgentRunCreate is schemas.AgentRunCreate
    assert agents.assert_run_can_execute is state.assert_run_can_execute


def test_database_model_registry_registers_all_domain_tables() -> None:
    Database("sqlite+pysqlite:///:memory:").init()

    expected_tables = {
        "workspaces",
        "projects",
        "workspace_members",
        "audit_logs",
        "workspace_gitlab_credentials",
        "git_repositories",
        "jobs",
        "project_modules",
        "module_mapping_rules",
        "test_cases",
        "case_drafts",
        "case_revisions",
        "case_review_cycles",
        "case_review_events",
        "workspace_review_settings",
        "import_batches",
        "import_case_drafts",
        "diff_analyses",
        "ai_suggestions",
        "test_plans",
        "plan_items",
        "release_reports",
        "workspace_ai_settings",
        "llm_providers",
        "model_profiles",
        "ai_invocation_logs",
        "agent_runs",
        "agent_tool_calls",
        "agent_staged_outputs",
        "agent_repository_sandboxes",
        "coverage_index_entries",
    }

    assert expected_tables <= set(Base.metadata.tables)


def test_create_app_keeps_domain_route_paths_registered() -> None:
    settings = Settings(database_url="sqlite+pysqlite:///:memory:", redis_url="redis://localhost:6379/15")
    app = create_app(settings)
    paths = {route.path for route in app.routes if hasattr(route, "path")}

    expected_paths = {
        "/api/workspaces",
        "/api/workspaces/{workspace_id}/projects",
        "/api/workspaces/{workspace_id}/gitlab-token",
        "/api/workspaces/{workspace_id}/repositories",
        "/api/workspaces/{workspace_id}/projects/{project_id}/imports",
        "/api/workspaces/{workspace_id}/projects/{project_id}/test-cases",
        "/api/workspaces/{workspace_id}/projects/{project_id}/review-cycles",
        "/api/workspaces/{workspace_id}/projects/{project_id}/diff-analyses",
        "/api/workspaces/{workspace_id}/projects/{project_id}/ai-suggestions/{suggestion_id}/candidate",
        "/api/workspaces/{workspace_id}/projects/{project_id}/plans",
        "/api/workspaces/{workspace_id}/projects/{project_id}/plans/{plan_id}/reports/draft",
        "/api/workspaces/{workspace_id}/ai-settings",
        "/api/workspaces/{workspace_id}/agent/runs/{run_id}/execute",
        "/api/workspaces/{workspace_id}/agent/memory/files",
    }

    assert expected_paths <= paths
