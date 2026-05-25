# ADR 0002: Human-Confirmed Module Trees and Code Mapping

## Status

Accepted

## Context

QualiForge needs module knowledge that both testers and AI agents can use. The module tree is the bridge between human test assets and repository evidence: test cases, diff analysis, regression recommendations, and release reports all depend on it.

The system must support more than Web/backend projects. A project may be a Web app, desktop app, CLI tool, SDK/library, embedded system, or streaming/media codec endpoint such as an FFmpeg-like repository. Therefore modules cannot be modeled as framework routes or backend services only.

The key product invariant is:

- Humans own the product or capability taxonomy.
- AI can infer, suggest, and explain technical bindings.
- AI suggestions do not become formal knowledge until a human confirms or edits them.

## Decision

### Module Tree

The module tree is a human-facing function or capability tree, not a code architecture tree.

For business applications it may look like:

```text
Account
  Login and Registration
  Permissions and Members

Test Assets
  Case Import
  Case Review
  Case Search
```

For streaming or media projects it may look like:

```text
Input and Ingest
Transport and Protocols
Codec Capabilities
Container Formats
Media Processing Pipeline
Playback and Rendering
Stability and Performance
Platform and Hardware Adaptation
```

The tree should normally stay at two to three levels:

- Level 1: product domain or capability domain.
- Level 2: independently testable feature or capability area.
- Level 3: optional sub-capability for complex areas.

Individual test scenarios should not become module nodes.

Each module should have:

- `name`: human display name, editable.
- `code`: stable project-level business code, not automatically changed by rename or move.
- `description`: one-sentence responsibility.
- `keywords`: structured human-provided or AI-suggested keywords.
- `owner` now, and structured owner/reviewer configuration later.

Modules remain a single-parent tree. Cross-cutting relationships should be expressed through tags, related modules, or future module links rather than making the tree a DAG.

### Project Type

Projects should support one primary project type and optional secondary project types.

Initial project type vocabulary:

- Web application
- Mobile app
- Desktop app
- CLI tool
- SDK/library
- Data or algorithm engine
- Streaming/media codec endpoint
- Embedded/firmware
- Other

Project type guides AI templates and scanning strategy. It does not hard-limit what mapping rules a user may create.

System project type templates provide only high-level capability skeletons. Project-specific modules are created from human input, repository scanning, and human confirmation.

### AI Suggestions and Staged Outputs

AI-generated module trees, mapping suggestions, refactor suggestions, case candidates, regression recommendations, and report drafts are reviewable staged outputs.

They are persistent and can be resumed across sessions, but they do not directly mutate formal business data.

Users can:

- accept a staged output
- edit and accept it
- reject it
- batch accept selected items

Acceptance creates or updates formal business objects according to the product workflow. Formal test assets, formal mapping rules, and release conclusions always require a human confirmation action.

### Module Mapping Rules

`ModuleMappingRule` connects a project module to technical evidence. It is project-scoped and may optionally be repository-scoped.

Formal mapping rules should support:

- `repository_id`: nullable; code-path rules should normally bind to a concrete repository.
- `rule_type`: the kind of mapped target.
- `pattern`: glob, identifier, API route, command, symbol, keyword, or similar.
- `relationship`: `primary`, `related`, `dependency`, or `evidence`.
- `status`: `active`, `stale`, or `archived`.
- `source`: `manual`, `ai_repository`, `ai_history`, `diff_confirmation`, or template/import source later.
- `ai_confidence`: AI's initial confidence.
- `confidence`: current composite confidence.
- `description` or `reason`: human-readable explanation.
- `evidence_refs`: structured evidence references, not large source snapshots.
- `accepted_from_output_id`: staged output origin when accepted from AI/template output.
- `verified_by` and `verified_at`: current human confirmation metadata.
- `stale_reason`: why a rule needs review.
- `conditions`: optional JSON for platform, language, build target, project type, or other constraints.

The first expanded `rule_type` set is:

```text
directory
file
api
service
command
library_api
symbol
package
build_target
config_key
database_migration
protocol
transport
format
codec
media_pipeline
asset_fixture
keyword
```

`media_pipeline` is intentionally high-level. It covers media processing chains such as encoding/decoding flow, filtering, transcoding, remuxing, capture/render, push/pull, synchronization, and buffering without over-modeling every media subsystem as a separate rule type.

### Pattern Semantics

Path-like mapping rules use glob semantics. Rules may support exclusions using `!pattern`; exclusions win over inclusions.

Examples:

```text
libavcodec/h264*
!libavcodec/h264_metadata*

backend/app/cases/**
!backend/app/cases/review_*
```

Matching is weighted, not boolean. Diff analysis and mapping confirmation should consider:

- relationship weight
- confidence
- verification status
- specificity score
- active vs stale lifecycle status

Specificity is intentionally simple and explainable:

- exact files are more specific than globs
- fewer wildcards are more specific
- longer fixed prefixes are more specific
- file and directory rules are usually stronger than keyword rules
- exclusions override inclusions

Code path rules default to case-sensitive matching. Keyword, command, API, and config-like rules may default to case-insensitive matching, with project or rule overrides later.

### Primary Ownership and Conflicts

The goal is at most one `primary` module per code path within a project/repository context. A path may still have multiple `related`, `dependency`, or `evidence` relationships.

The system does not need to reject overlapping primary rules at write time. Repository scans and diff analysis should surface primary conflicts and ask humans to resolve them by narrowing a pattern or changing a relationship.

### Rule Lifecycle

`active` rules participate normally in diff analysis and recommendation.

`stale` rules weakly participate and are clearly marked as needing review.

`archived` rules are retained for history and normally do not participate.

Rules become stale when evidence meaningfully changes, for example:

- module responsibility or keywords changed substantially
- the pattern no longer matches files
- many matched files moved or disappeared
- repository scans find stronger contradictory ownership
- users repeatedly correct diff impact results

Light renames do not automatically stale all rules.

### Evidence

Evidence references store traceable pointers and summaries, not full source files.

Examples:

```json
[
  {
    "type": "file",
    "repository_id": "repo_123",
    "ref": "main",
    "commit_sha": "abc123",
    "path": "libavcodec/h264dec.c",
    "symbol": "ff_h264_decoder",
    "line_start": 123,
    "line_end": 180,
    "reason": "decoder registration"
  }
]
```

Source snippets can be read from the repository sandbox when needed. The database should keep structured references, short summaries, hashes, and line ranges.

### Repository Analysis Boundary

For MVP, AI may read source code for static analysis. It must not execute project code.

Allowed:

- clone/fetch/checkout/read
- `git diff`, `git show`, `git ls-files`
- `rg`
- static parsers, AST parsers, tree-sitter, symbol extraction
- manifest and documentation parsing

Not allowed by default:

- running project tests
- running build scripts
- starting services
- running migrations
- connecting to business databases
- executing arbitrary repository scripts

Repository scanning should build a reusable index keyed by `repository_id + commit_sha`. MVP indexing should include file inventory and lightweight symbol/entrypoint information. Full dependency or call graphs are deferred.

### Tests and Assets

Test files and media/binary assets can participate as evidence, but they are not strong implementation mappings by default.

Test files can help infer module ownership. They become formal module mappings only when humans confirm that they represent module test assets or evidence.

Media and binary assets are indexed lightly by path, type, size, naming, and manifest references. Their contents are not parsed in MVP.

### Module and Case Ownership

Formal test cases keep one primary module. Related coverage can be represented later through related module IDs, coverage tags, or coverage index entries.

AI-generated case candidates may include suggested primary and related modules, but reviewers must be able to confirm or edit module assignment before formal acceptance.

Module merges and splits require explicit migration previews:

- merge moves current assets to the target module, archives the source module, and records audit
- split proposes assignment of cases, mappings, and keywords before human confirmation
- source modules are not hard-deleted when historical meaning must be preserved

## Consequences

This design keeps module knowledge human-centered while letting AI do the tedious technical binding work.

It also creates a durable review boundary: AI outputs are persistent, inspectable, and useful across sessions, but only accepted outputs become formal test or mapping assets.

The tradeoff is added data-model complexity:

- module mapping rules need richer lifecycle and evidence fields
- staged outputs must become a reusable project-level mechanism, not only an agent workbench detail
- repository scans need indexing and preflight validation
- UI must support module-centered review and conflict-centered review

The benefit is a model that can handle Web apps, desktop apps, CLI tools, libraries, and streaming/media projects without forcing code directories to become the product taxonomy.

