# Module Mapping Implementation Plan

## Goal

Build the first usable loop for human-owned module trees and AI-assisted code mapping:

```text
project type and module hints
-> module tree draft or manual module tree
-> AI/static repository mapping suggestions
-> human review and edit
-> formal ModuleMappingRule records
-> diff analysis and regression recommendation use active rules
```

This plan intentionally avoids implementing the whole future system at once. The first milestone should make module mapping useful and auditable without building a full code graph or template marketplace.

## Phase 1: Formalize Module And Mapping Data

### Backend Data Model

Extend `ProjectModule`:

- `keywords: list[str]` stored as JSON.
- keep `code` as the stable project-level module code.
- add project-level uniqueness for non-empty `code`.

Extend `ModuleMappingRule`:

- `repository_id: str | None`
- expanded `rule_type`
- `relationship: primary | related | dependency | evidence`
- `status: active | stale | archived`
- `ai_confidence: int`
- `confidence: int`
- `evidence_refs: list[dict]`
- `accepted_from_output_id: str | None`
- `verified_by: str`
- `verified_at: datetime | None`
- `stale_reason: str`
- `conditions: dict`
- `case_sensitive: bool | None`

Keep `source`, `description`, `created_at`, and `updated_at`.

### API

Update module create/update payloads:

- accept `keywords`
- return `keywords`

Update mapping create/update/list payloads:

- accept and return the new fields
- allow filtering by `repository_id`, `relationship`, and `status`
- default list endpoints should return active rules unless callers ask for stale/archived rules

### Audit

Audit before/after snapshots should include:

- module keywords
- mapping relationship/status
- repository binding
- confidence fields
- evidence count
- verification metadata

### Tests

Add focused API tests for:

- module keywords create/update/list/tree serialization
- project-unique module `code`
- expanded mapping rule types
- mapping relationship/status defaults
- mapping filtering by status and repository
- archived rules not returned by default if that default is adopted
- evidence refs round trip without storing large source bodies

## Phase 2: UI Support For Manual First Mapping

Update the Module Mapping Admin screen so humans can maintain the new model before AI automation exists.

### Module Editor

Add:

- keywords field
- clearer copy that modules are feature/capability areas, not code directories

Keep:

- name
- code
- slug
- description
- owner
- status

### Mapping Rule Editor

Add controls for:

- repository selector, optional
- rule type
- relationship
- lifecycle status
- pattern
- source
- AI confidence
- current confidence
- reason/description
- evidence refs as compact JSON textarea or read-only preview for MVP

The first UI can remain dense and utilitarian. It does not need a full conflict resolution workflow yet.

### Labels

Add labels for:

- expanded mapping rule types
- relationship values
- mapping statuses

## Phase 3: Staged Output As The AI Review Boundary

Generalize staged outputs into a project-level reviewable AI output mechanism.

Current agent staged outputs can be reused, but module mapping should not be permanently tied to agent workbench UI.

Minimum fields:

- `workspace_id`
- `project_id`
- optional `agent_run_id`
- optional `job_id`
- `output_type`
- `status: staged | accepted | rejected | superseded`
- `title`
- `payload`
- `evidence_refs`
- `quality_result`
- `created_by`
- `created_at`
- `decided_by`
- `decided_at`
- `decision_summary`

Initial output types:

- `module_tree_draft`
- `module_mapping_suggestions`
- `module_refactor_suggestion`
- existing case/regression/report output types

Acceptance handlers should convert accepted payloads into formal modules or mapping rules.

## Phase 4: Repository Static Index

Create a lightweight repository index keyed by `repository_id + commit_sha`.

### MVP Index Content

Store:

- file path
- directory
- extension/language guess
- file role: source, test, doc, config, asset, generated, vendor, build output
- size and content hash
- short summary or keywords when available
- lightweight symbols/entrypoints when cheap to extract
- manifest references

Do not store:

- full source files
- large snippets
- binary contents

### Static Analysis Boundary

Allowed:

- git read commands
- ripgrep
- static parsers
- manifest parsing

Disallowed by default:

- tests
- builds
- services
- migrations
- arbitrary repo scripts

## Phase 5: AI/Static Mapping Suggestions

Generate `module_mapping_suggestions` staged outputs from:

- module name, description, keywords, and code
- project type
- repository index
- paths, symbols, entrypoints, docs, tests, and assets
- existing mappings and stale mappings

Suggestion item shape:

- target module
- repository
- rule type
- pattern
- relationship
- ai confidence
- proposed current confidence
- reason
- positive evidence refs
- caution or negative evidence
- suggested status

### Preflight Checks

Before acceptance, validate:

- pattern matches at least one target when path-like
- duplicate or near-duplicate existing rules
- primary conflicts
- overly broad matches
- vendor/third-party/generated/build output matches
- stale repository ref or missing repository

Defaults:

- vendor/third-party/dependency/build/generated output is excluded from suggestions
- test files are evidence by default, not strong primary mappings
- exclusions beat inclusions

## Phase 6: Diff Analysis Integration

Update diff analysis to use formal mapping fields.

Rules:

- `active` participates normally
- `stale` participates weakly and is marked for review
- `archived` does not participate by default
- `primary` drives core impact
- `related` drives secondary impact
- `dependency` drives risk hints
- `evidence` is not treated as direct implementation impact

Diff output should eventually separate:

- primary impact
- related impact
- dependency or observation risk
- mapping conflicts
- stale mapping warnings

Regression recommendations should separate:

- core regression
- extended regression
- observation items

## Phase 7: Import/Export And Templates

Add YAML or JSON import/export for:

- module tree
- module keywords
- mapping rules
- evidence refs where appropriate

Imports become staged outputs first. They do not directly overwrite formal modules or mappings.

Add two template concepts later:

- system project type templates
- team project module templates

Team templates may include mapping patterns, but template mappings default to staged suggestions unless the user explicitly trusts them.

## Suggested First PR

The first implementation PR should be deliberately narrow:

1. Add `keywords` to modules.
2. Add mapping `relationship`, `status`, `ai_confidence`, `evidence_refs`, and optional `repository_id`.
3. Expand `MappingRuleType`.
4. Update API schemas and backend tests.
5. Update the Module Mapping Admin UI enough to create and edit these fields manually.

Do not include in the first PR:

- AI generation
- repository index
- staged output generalization
- conflict resolution UI
- import/export
- project type templates

## Acceptance Criteria For The First PR

- A WorkspaceOwner can create a module with keywords.
- A WorkspaceOwner can create a mapping rule with repository scope, relationship, status, confidence, and evidence refs.
- API responses expose the new fields in module list, tree, and mapping list endpoints.
- Tests prove the new fields round trip.
- Existing diff/import behavior still works with default active primary-like mappings.
- Existing UI flows for creating modules and mapping rules still work.

