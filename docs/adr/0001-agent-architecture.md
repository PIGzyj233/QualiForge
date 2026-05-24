# ADR 0001: AI Agent Architecture

## Status

Accepted

## Context

QualiForge needs an AI agent that can help QA teams turn imported historical cases, Git repository context, diffs, existing coverage, and release facts into reviewable test assets.

The agent must not be a thin text-generation feature. It needs to work with tools, read code, inspect imports, search existing coverage, create staged outputs, and collaborate with users through conversation. At the same time, QualiForge's product invariants still apply:

- AI can create candidates, recommendations, summaries, and drafts, but cannot bypass human review for formal test assets.
- Git repository access is read-oriented. The agent may clone, fetch, checkout, diff, grep, and read files in the sandbox, but must not modify code content.
- Code, imported files, logs, and repository documents are untrusted context. They can be used as evidence, but cannot issue instructions to the agent.
- The system must remain private/self-hosted first and support auditable, recoverable long-running work.

## Decision

Use a layered agent architecture:

- Temporal is the outer durable execution layer.
- LangGraph is the agent and subagent state-machine layer.
- LiteLLM Proxy is the model gateway.
- QualiForge owns the business audit log, model invocation log, memory version history, coverage index, and staged outputs.

### Temporal

Temporal manages `AgentRun` lifecycle:

- durable workflow execution
- queueing
- retries
- cancellation
- timeouts
- waiting for user input or confirmation via signals
- long-running and heavyweight child workflows

Temporal does not decide what the agent should do next. It provides durable execution around that decision process.

### LangGraph

LangGraph manages the agent reasoning and tool-decision state:

- direct answer mode for small questions
- specialized graphs for import cleanup, diff analysis, case generation, and report drafting
- supervisor-agent orchestration
- dynamic subagent selection
- graph checkpointing
- human-in-the-loop interruption points

Specialized graphs use a deterministic skeleton with a bounded autonomous tool loop:

```text
load_context -> plan -> tool_loop -> synthesize -> verify -> write_staged_outputs -> summarize
```

The supervisor agent may decide whether to use subagents, which subagents to use, how many to launch, whether they run serially or in parallel, and whether a critic subagent is required. This autonomy must be stated in the supervisor system prompt.

### Subagents

Subagents are selected dynamically by the supervisor from a registered set. Initial subagent types include:

- `CodeAnalysisSubAgent`
- `ImportAnalysisSubAgent`
- `CaseDesignSubAgent`
- `RegressionScopeSubAgent`
- `CriticSubAgent`
- `ReportDraftSubAgent`

Subagents can read, analyze, and propose structured results. They cannot directly write business objects. The supervisor owns final consolidation and staged-output writing.

Normal subagents run as LangGraph subgraphs. Heavyweight sub-tasks, such as large repository scans or large batch imports, may run as Temporal child workflows.

### LiteLLM Proxy

The backend and agents call a QualiForge `ModelGateway` interface. The v1 implementation points to LiteLLM Proxy through an OpenAI-compatible API.

Agents must not call upstream model providers directly.

LiteLLM Proxy handles model aliasing, routing, fallback, rate limits, and cost governance. QualiForge still owns `AIInvocationLog` as the product audit source for model calls.

Model selection is configurable by purpose, agent role, and subagent type. The supervisor can use a stronger model, while deterministic subagents can use cheaper models. Model calls retry up to three times according to the configured retry policy.

### Agent Domain Objects

`AgentRun` is a first-class domain object. It is not the same as `AIInvocationLog`.

Core agent records:

- `AgentConversation`: long-lived user-agent conversation container.
- `AgentRun`: one executable unit of work.
- `AgentMessage`: user and agent conversation messages.
- `AgentToolCall`: audited tool invocation record.
- `AgentApproval`: pending or completed human gate.
- `AgentStagedOutput`: reviewable agent output before business-object acceptance.
- `AIInvocationLog`: one model call, linked to an agent run or tool call.

### Tools

All tools are exposed through a Tool Registry with schemas, permissions, budgets, audit behavior, and idempotency keys.

Tool permission levels:

- `read`: automatic execution.
- `safe_mutation`: automatic execution only for staging and operational records, with audit.
- `human_gate`: requires explicit user confirmation.

The agent can:

- read and analyze import files
- sync Git repositories
- checkout refs in the sandbox
- grep and read code
- read existing cases, modules, mappings, diffs, reports, and memory
- create staged outputs
- create operational audit records and run status updates

The agent cannot:

- modify code content
- run arbitrary shell commands
- run project tests or services
- access business databases
- approve reviews
- bypass the formal test-case review flow

Git clone, fetch, checkout, diff, show, grep, and read operations are allowed inside the sandbox because they do not modify code content.

### Code Reading

Code reading follows a Codex-style workflow but with strong typed tools instead of free-form shell:

- `code_rg_files`
- `code_search`
- `code_read_range`
- `code_read_numbered_range`
- `git_status`
- `git_diff`
- `git_show_file`
- `parallel_code_read`
- `repo_context_resources`

The implementation may use `rg`, `sed`, `nl`, and `git` internally, but the agent must call typed tools. Paths are sandbox checked, commands are allowlisted, outputs are truncated, and all calls are audited.

### Memory

Use Markdown-first memory:

- Workspace memory for team-wide rules.
- Project memory for project-specific testing and domain knowledge.
- User memory for personal preferences.
- Daily memory files for short-term run summaries.
- Curated long-term memory files for stable facts and preferences.

Markdown files are the source of truth. PostgreSQL stores indexes, version history, audit records, checksums, and permissions.

Users may edit memory through QualiForge. Every edit is versioned and auditable. Rollback writes a prior version as a new version.

### Coverage Index

`CoverageIndex` is a core data model. It captures coverage signals from formal cases, imported cases, AI candidates, staged outputs, temporary plan items, diffs, code evidence, and observability evidence.

Coverage signals are gradual and confidence-scored. Imported historical cases may only have text/domain signals at first. Code-link signals can be added later by agent analysis or human confirmation.

The agent must perform coverage lookup and duplicate detection before creating case candidates.

### Staging

Execute mode writes staged outputs first. Staged outputs are persistent, auditable, reviewable, and recoverable, but they do not immediately become business objects.

Users can accept, edit and accept, reject, or batch accept staged outputs. Acceptance creates or updates business objects according to existing review rules.

Coverage entries have states such as `staged`, `candidate`, and `formal`.

### Evidence

All generated outputs must reference structured evidence. `EvidenceRef` is a foundational object used by staged outputs, candidates, recommendations, reports, coverage signals, and audit explanations.

Evidence can reference:

- import rows, sheets, or cells
- code files, refs, and line ranges
- grep results
- diff hunks and analyses
- test cases and revisions
- module mapping rules
- user messages
- memory entries
- log, audit, metric, and trace signals

The system stores decision summaries and evidence references. It does not store or expose full chain-of-thought.

### Observability

Agent-generated case candidates should include observable validation points when possible:

- logs
- request IDs
- trace IDs
- job IDs
- entity IDs
- audit events
- metrics
- background job states
- frontend, API, database, queue, and report signals

If a high-risk flow lacks observable signals, the agent records an observability gap instead of inventing one.

### UI

The UI is an agent workbench, not a chat-only interface:

- conversation panel
- run progress and tool/subagent status
- budget usage
- pending approvals
- staged output review
- evidence drawer
- coverage and duplicate-detection views
- memory management with audit and rollback

### Preview and Execute Modes

Preview mode performs read-only analysis.

Execute mode allows the agent to write staged outputs and operational records. It still does not allow direct promotion to formal assets.

### Budgeting

Budgets are configurable at multiple levels:

- system hard cap
- workspace default
- project override
- purpose/model profile
- run override

Budgets include tool calls, subagents, parallel subagents, model calls, wall time, source context size, candidate count, and cost. When a budget is exceeded, the run pauses and asks the user whether to continue, narrow scope, or stop.

## Consequences

This design gives QualiForge a durable, tool-using, auditable agent that can behave flexibly without becoming an uncontrolled shell or direct database writer.

The cost is added infrastructure and implementation complexity:

- Temporal must be deployed and operated.
- LiteLLM Proxy must be deployed and configured.
- LangGraph checkpoints, tool registry, memory files, staging, and coverage indexing must be designed carefully.
- The UI must support review workflows instead of treating agent output as plain chat text.

The design intentionally separates durable execution, agent reasoning, model gateway concerns, business audit, and product data truth. This keeps the architecture evolvable even if one underlying framework changes later.

## Implementation Order

Implement in phases:

1. Add agent domain models: conversation, run, messages, staged outputs, evidence refs, tool calls, approvals, and coverage index.
2. Add LiteLLM Proxy and the `ModelGateway` abstraction with invocation logging.
3. Add the typed code-reading and import-reading tool registry.
4. Add the minimal LangGraph supervisor for direct answer mode and case generation.
5. Add Temporal workflows, signals, cancellation, retries, and long-running run execution.
6. Add dynamic subagents, memory curator, observability gap detection, and parallel execution.
7. Add the agent workbench UI and memory management UI.

