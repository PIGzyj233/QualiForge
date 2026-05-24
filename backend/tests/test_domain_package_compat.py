from __future__ import annotations

import importlib

from app.config import Settings
from app.database import Database
from app.main import create_app
from app.platform.database import Base


def test_legacy_module_paths_alias_domain_modules() -> None:
    module_pairs = [
        ("app.config", "app.platform.config", ["Settings"], True),
        ("app.database", "app.platform.database", ["Database", "Base"], True),
        ("app.telemetry", "app.platform.telemetry", ["agent_span"], True),
        ("app.gitlab", "app.git.gitlab", ["GitRepository", "ensure_safe_sandbox_path"], True),
        ("app.code_tools", "app.git.code_tools", ["code_search", "CodeReadResult"], True),
        ("app.case_domain", "app.cases.domain", ["TestCase", "CaseDraft"], True),
        ("app.case_imports", "app.cases.imports", ["ImportBatch", "safe_filename"], True),
        ("app.case_reviews", "app.cases.reviews", ["WorkspaceReviewSettings", "build_case_response"], True),
        ("app.diff_analysis", "app.cases.diff_analysis", ["DiffAnalysis", "run_analysis"], True),
        ("app.ai_suggestions", "app.cases.ai_suggestions", ["AISuggestion"], True),
        ("app.ai_config", "app.ai.config", ["WorkspaceAISettings", "AIInvocationLog"], True),
        ("app.model_gateway", "app.ai.model_gateway", ["build_model_gateway"], True),
        ("app.test_plans", "app.planning.test_plans", ["TestPlan", "PlanItem"], False),
        ("app.release_reports", "app.planning.release_reports", ["ReleaseReport"], True),
        ("app.workspaces", "app.workspace.routes", ["Workspace", "AuditLog"], True),
        ("app.modules", "app.cases.modules", ["ProjectModule", "ModuleMappingRule"], True),
        ("app.agent_graph", "app.agents.graph", ["AgentGraphExecutor", "execute_agent_graph"], True),
        ("app.agent_memory", "app.agents.memory", ["list_memory_files"], True),
        ("app.agent_temporal", "app.agents.temporal", ["AgentTemporalUnavailable"], True),
        ("app.agent_workflows", "app.agents.workflows", ["AgentRunWorkflow"], True),
        ("app.agent_activities", "app.agents.activities", ["mark_agent_run_failed_with_settings"], True),
    ]

    for legacy_name, domain_name, attributes, same_module in module_pairs:
        legacy = importlib.import_module(legacy_name)
        domain = importlib.import_module(domain_name)
        if same_module:
            assert legacy is domain
        for attribute in attributes:
            assert getattr(legacy, attribute) is getattr(domain, attribute)


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
