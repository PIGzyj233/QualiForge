# ADR 0003: Centralize ModuleMapping Rule Evaluation

## Status

Accepted

## Context

ADR 0002 defines `ModuleMappingRule` as the formal bridge between a human-facing module tree and repository evidence. The current implementation stores the right fields, but rule evaluation is still shallow: DiffAnalysis, Case import, ModuleMapping Admin, and future Agent mapping flows each need to know pieces of rule semantics.

That spreads knowledge about `relationship` weights, `status` lifecycle, repository scope, case sensitivity, path glob matching, text matching, and primary ownership conflicts across callers. It also makes `case_text` evidence risky: historical test case rows are not repository paths, so directory and file rules should not silently participate in import-time inference.

## Decision

Create a deep Module for ModuleMapping rule evaluation. Its Interface should hide rule semantics behind two entry points:

```python
evaluate_mapping(evidence, rule_set) -> MappingEvaluation
preflight_rule(candidate_rule, rule_set, sample_inventory=None) -> RulePreflight
```

The Module owns:

- rule applicability by evidence kind
- repository scoping
- path normalization
- glob matching and exclusions
- case-sensitivity defaults
- text evidence matching
- `relationship` and `status` weighting
- specificity scoring
- primary ownership conflict detection
- stale, archived, duplicate, and over-broad rule warnings

Callers pass a snapshot-style `rule_set`, not SQLAlchemy ORM objects. The Interface should accept explicit evidence kinds:

- `code_change`: used by DiffAnalysis; may evaluate path, content, and structure evidence.
- `case_text`: used by Case import; only text-oriented rule types participate by default, such as `keyword`, `api`, `command`, `symbol`, and `config_key`.
- `repository_scan`: used by future repository indexing or AI mapping suggestions; may evaluate inventory, symbol, and path evidence.

`directory` and `file` rules do not participate in `case_text` evaluation unless a future ADR explicitly changes that rule. Imported historical cases can still match a Module directly by module name, slug, path label, or code before rule evaluation runs.

`preflight_rule` is the formal Interface for ModuleMapping Admin and accepted AI staged outputs. It should report warnings and blocking conflicts before a rule becomes formal knowledge, including duplicate rules, repository mismatch, broad path matches, primary conflicts, stale rule reasoning gaps, and generated/vendor/test-file risk when sample inventory is available.

The dependency category is primarily in-process. If preflight later samples Git Sandbox inventory, that sampling should sit behind an internal local-substitutable Adapter; the external Interface should remain stable.

## Consequences

This concentrates ModuleMapping behaviour in one place and makes ADR 0002 executable instead of caller-specific.

Benefits:

- DiffAnalysis, Case import, Agent flows, and ModuleMapping Admin get the same rule semantics.
- Tests can target the evaluator Interface instead of duplicating assertions across callers.
- New rule types or weighting changes have locality.
- `case_text` inference avoids path-rule false positives.

Costs:

- A snapshot model is needed between ORM persistence and the evaluator.
- Existing tests for DiffAnalysis and Case import should be moved toward evaluator-level coverage.
- The first implementation must preserve current behaviour where callers already depend on it, then tighten semantics behind explicit tests.

## Implementation Order

1. Add `backend/app/cases/mapping_evaluator.py` with snapshot types, evidence types, evaluation results, and preflight results.
2. Move DiffAnalysis matching into `evaluate_mapping(code_change, rule_set)`.
3. Move Case import module inference into `evaluate_mapping(case_text, rule_set)`, keeping direct module aliases as a pre-rule step.
4. Add `preflight_rule` and call it from ModuleMapping Admin save paths and AI staged-output acceptance.
5. Update tests so the evaluator Interface is the primary test surface, with caller tests only proving integration.
