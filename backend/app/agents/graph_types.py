from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from app.agents import (
    AgentRepositorySandbox,
    AgentRun,
    AgentStagedOutput,
    AgentToolCall,
    CoverageEntryCreate,
    EvidenceRef,
)


class AgentGraphConflict(Exception):
    """Raised when a run cannot execute because of user-correctable state."""


class AgentPolicyViolation(Exception):
    """Raised when workspace AI data policy rejects agent execution."""


class AgentBudgetExceeded(RuntimeError):
    """Raised when a run reaches a configured v1 budget limit."""


class AgentRunCancelled(RuntimeError):
    """Raised when an AgentRun receives a cancellation request."""


class AgentGraphState(TypedDict, total=False):
    workspace_id: str
    run_id: str
    repository_id: str
    requested_ref: str
    resolved_ref: str
    sandbox_id: str
    worktree_path: str
    context: dict[str, Any]
    tool_results: dict[str, Any]
    subagent_plan: dict[str, Any]
    llm_raw: str
    candidates: list[dict[str, Any]]
    module_tree_draft: dict[str, Any]
    verified_module_tree_draft: dict[str, Any]
    verified_candidates: list[dict[str, Any]]
    reuse_recommendations: list[dict[str, Any]]
    subagent_results: dict[str, Any]
    staged_output_ids: list[str]
    summary: str


class GeneratedCaseCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=240)
    steps: list[str] = Field(min_length=2)
    expected_result: str = Field(min_length=1, max_length=2000)
    risk: str = Field(min_length=1, max_length=80)
    priority: str = Field(min_length=1, max_length=32)
    module_key: str = Field(min_length=1, max_length=80)
    unmapped_reason: str = Field(default="", max_length=500)
    observability: dict[str, Any]
    evidence_refs: list[EvidenceRef] = Field(min_length=1)
    duplicate_result: dict[str, Any]
    coverage_entries: list[CoverageEntryCreate] = Field(min_length=1)


class GeneratedCandidateEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_candidates: list[GeneratedCaseCandidate] = Field(min_length=1)


class GeneratedModuleDraftItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: str = Field(min_length=1, max_length=80)
    parent_draft_id: str | None = Field(default=None, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=80)
    code: str = Field(default="", max_length=48)
    description: str = Field(default="", max_length=500)
    keywords: list[str] = Field(default_factory=list, max_length=30)
    source_paths: list[str] = Field(min_length=1, max_length=20)
    rationale: str = Field(min_length=1, max_length=700)
    confidence: int = Field(default=70, ge=0, le=100)
    evidence_refs: list[EvidenceRef] = Field(min_length=1)


class GeneratedModuleTreeDraftEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=1000)
    modules: list[GeneratedModuleDraftItem] = Field(min_length=1)


@dataclass(frozen=True)
class SubAgentSpec:
    name: str
    stage: str
    required: bool
    parallel_group: str
    trigger_tokens: frozenset[str]
    purpose: str


SUBAGENT_REGISTRY: dict[str, SubAgentSpec] = {
    "CodeAnalysisSubAgent": SubAgentSpec(
        name="CodeAnalysisSubAgent",
        stage="code_analysis",
        required=True,
        parallel_group="read_analysis",
        trigger_tokens=frozenset({"code", "repo", "repository", "diff", "source", "file", "audit", "log"}),
        purpose="Read repository structure and code evidence.",
    ),
    "RegressionScopeSubAgent": SubAgentSpec(
        name="RegressionScopeSubAgent",
        stage="coverage_lookup",
        required=False,
        parallel_group="read_analysis",
        trigger_tokens=frozenset({"regression", "reuse", "duplicate", "coverage", "existing", "extend"}),
        purpose="Find existing coverage that should be reused or extended.",
    ),
    "ImportAnalysisSubAgent": SubAgentSpec(
        name="ImportAnalysisSubAgent",
        stage="import_analysis",
        required=False,
        parallel_group="read_analysis",
        trigger_tokens=frozenset({"import", "imported", "historical", "csv", "xlsx", "spreadsheet", "cleanup", "mapping"}),
        purpose="Analyze imported test assets, mappings, duplicates, and cleanup gaps.",
    ),
    "CaseDesignSubAgent": SubAgentSpec(
        name="CaseDesignSubAgent",
        stage="case_design",
        required=True,
        parallel_group="case_design",
        trigger_tokens=frozenset({"case", "test", "candidate", "scenario", "coverage"}),
        purpose="Generate structured candidate cases from verified evidence.",
    ),
    "ModuleTreeDraftSubAgent": SubAgentSpec(
        name="ModuleTreeDraftSubAgent",
        stage="module_tree_draft",
        required=False,
        parallel_group="module_tree_draft",
        trigger_tokens=frozenset({"module", "modules", "目录", "模块", "mapping", "tree", "architecture"}),
        purpose="Generate a reviewable module tree draft from repository evidence.",
    ),
    "CriticSubAgent": SubAgentSpec(
        name="CriticSubAgent",
        stage="critic",
        required=False,
        parallel_group="critic",
        trigger_tokens=frozenset({"risk", "critical", "audit", "security", "payment", "refund", "observability"}),
        purpose="Check evidence support, duplication risk, and observability gaps.",
    ),
    "ReportDraftSubAgent": SubAgentSpec(
        name="ReportDraftSubAgent",
        stage="report_draft",
        required=False,
        parallel_group="report_draft",
        trigger_tokens=frozenset({"report", "release", "summary", "decision", "draft", "markdown"}),
        purpose="Propose report-ready summaries from structured run, risk, and coverage facts.",
    ),
}


@dataclass(frozen=True)
class AgentRunExecutionResult:
    run: AgentRun
    summary: str
    staged_outputs: list[AgentStagedOutput]
    tool_calls: list[AgentToolCall]
    sandboxes: list[AgentRepositorySandbox]


class CodeRgFilesInput(BaseModel):
    path: str = "."
    glob: str | None = None
    max_results: int = Field(default=500, ge=1, le=1000)


class CodeSearchInput(BaseModel):
    pattern: str = Field(min_length=1, max_length=500)
    path: str = "."
    max_results: int = Field(default=100, ge=1, le=500)


class CodeReadRangeInput(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


class GitShowFileInput(BaseModel):
    path: str = Field(min_length=1, max_length=500)


class CoverageLookupInput(BaseModel):
    query: str = Field(default="", max_length=1000)
    module_key: str = Field(default="", max_length=80)
    max_results: int = Field(default=40, ge=1, le=100)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    permission_level: str
    input_model: type[BaseModel]
    budget_cost: int
    audit_policy: str
    handler: Callable[[BaseModel], Any]
    input_summary: Callable[[BaseModel], str]
    output_summary: Callable[[Any], str]


