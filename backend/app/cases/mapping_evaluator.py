from __future__ import annotations

import fnmatch
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Literal


EvidenceKind = Literal["code_change", "case_text", "repository_scan"]

PATH_RULE_TYPES = {"directory", "file", "package", "build_target", "database_migration", "asset_fixture"}
CASE_TEXT_RULE_TYPES = {
    "keyword",
    "api",
    "command",
    "symbol",
    "config_key",
    "service",
    "library_api",
    "protocol",
    "transport",
    "format",
    "codec",
    "media_pipeline",
}
TEXT_RULE_TYPES = CASE_TEXT_RULE_TYPES | {"keyword"}
RELATIONSHIP_WEIGHT = {"primary": 1.0, "related": 0.75, "dependency": 0.55, "evidence": 0.0}
STATUS_WEIGHT = {"active": 1.0, "stale": 0.5, "archived": 0.0}
RISKY_PATH_SEGMENTS = {
    "vendor": "vendor_path_match",
    "third_party": "vendor_path_match",
    "third-party": "vendor_path_match",
    "node_modules": "vendor_path_match",
    "generated": "generated_path_match",
    "gen": "generated_path_match",
    "dist": "build_output_path_match",
    "build": "build_output_path_match",
    "target": "build_output_path_match",
    "__pycache__": "build_output_path_match",
}


@dataclass(frozen=True)
class ModuleSnapshot:
    id: str
    name: str
    slug: str
    code: str = ""
    path: str = ""
    path_label: str = ""
    status: str = "active"


@dataclass(frozen=True)
class RuleSnapshot:
    module_id: str
    rule_type: str
    pattern: str
    id: str = ""
    repository_id: str | None = None
    relationship: str = "primary"
    status: str = "active"
    confidence: int = 100
    case_sensitive: bool | None = None
    conditions: dict[str, Any] = field(default_factory=dict)
    stale_reason: str = ""
    source: str = ""
    ai_confidence: int = 0


@dataclass(frozen=True)
class MappingRuleSet:
    modules: tuple[ModuleSnapshot, ...] = ()
    rules: tuple[RuleSnapshot, ...] = ()

    @property
    def modules_by_id(self) -> dict[str, ModuleSnapshot]:
        return {module.id: module for module in self.modules}


@dataclass(frozen=True)
class MappingEvidence:
    kind: EvidenceKind
    repository_id: str | None = None
    path: str = ""
    content: str = ""
    structures: tuple[dict[str, Any], ...] = ()
    text: str = ""


@dataclass(frozen=True)
class MappingIssue:
    severity: Literal["blocker", "warning"]
    code: str
    reason: str
    rule_id: str | None = None
    module_id: str | None = None
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass(frozen=True)
class MappingMatch:
    rule: RuleSnapshot
    module: ModuleSnapshot | None
    score: int
    specificity: int
    evidence: str


@dataclass(frozen=True)
class MappingEvaluation:
    best_match: MappingMatch | None
    matches: tuple[MappingMatch, ...]
    evidence: tuple[str, ...]
    warnings: tuple[MappingIssue, ...] = ()
    primary_conflicts: tuple[MappingIssue, ...] = ()


@dataclass(frozen=True)
class RulePreflight:
    passed: bool
    blocker_count: int
    warning_count: int
    issues: tuple[MappingIssue, ...]
    matched_sample_count: int = 0
    sample_paths: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "blocker_count": self.blocker_count,
            "warning_count": self.warning_count,
            "issues": [issue.to_dict() for issue in self.issues],
            "matched_sample_count": self.matched_sample_count,
            "sample_paths": list(self.sample_paths),
        }


def normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def module_aliases(module: ModuleSnapshot) -> set[str]:
    aliases = {module.name.lower(), module.slug.lower(), module.path.lower(), module.path_label.lower()}
    if module.code:
        aliases.add(module.code.lower())
    return {alias for alias in aliases if alias}


def _pattern_parts(pattern: str) -> tuple[list[str], list[str], list[MappingIssue]]:
    includes: list[str] = []
    exclusions: list[str] = []
    issues: list[MappingIssue] = []
    raw_parts = [part.strip() for part in re.split(r"\r?\n", pattern or "") if part.strip()]
    for raw in raw_parts:
        if raw.startswith("!"):
            exclusion = raw[1:].strip()
            if not exclusion:
                issues.append(MappingIssue("blocker", "malformed_pattern", "Exclusion patterns must include text after '!'."))
            else:
                exclusions.append(exclusion)
        else:
            includes.append(raw)
    if not includes:
        issues.append(MappingIssue("blocker", "malformed_pattern", "Mapping rules must include at least one non-exclusion pattern."))
    return includes, exclusions, issues


def _case_sensitive(rule: RuleSnapshot) -> bool:
    if rule.case_sensitive is not None:
        return rule.case_sensitive
    return rule.rule_type in PATH_RULE_TYPES


def _repository_applies(rule: RuleSnapshot, evidence: MappingEvidence) -> bool:
    return not evidence.repository_id or not rule.repository_id or rule.repository_id == evidence.repository_id


def _candidate_text(pattern: str, case_sensitive: bool) -> str:
    text = pattern.strip().strip("*").strip()
    return text if case_sensitive else text.lower()


def _structure_text(structures: Iterable[dict[str, Any]]) -> str:
    return " ".join(str(item.get("name", "")) for item in structures)


def _structure_types(structures: Iterable[dict[str, Any]]) -> set[str]:
    return {str(item.get("type") or "") for item in structures}


def _compare_text(value: str, case_sensitive: bool) -> str:
    return value if case_sensitive else value.lower()


def _glob_match_path(rule_type: str, path: str, pattern: str) -> bool:
    normalized = normalize_path(path)
    rule_pattern = normalize_path(pattern)
    if rule_type == "directory":
        directory = rule_pattern.rstrip("/")
        return fnmatch.fnmatchcase(normalized, rule_pattern) or normalized.startswith(directory + "/") or normalized == directory
    if rule_type in {"file", "package", "build_target", "asset_fixture"}:
        return fnmatch.fnmatchcase(normalized, rule_pattern) or normalized.endswith(rule_pattern)
    if rule_type == "database_migration":
        return fnmatch.fnmatchcase(normalized, rule_pattern) or rule_pattern in normalized
    return fnmatch.fnmatchcase(normalized, rule_pattern)


def _path_match(rule: RuleSnapshot, path: str) -> bool:
    includes, exclusions, issues = _pattern_parts(rule.pattern)
    if issues or not path:
        return False
    case_sensitive = _case_sensitive(rule)
    candidate_path = normalize_path(path) if case_sensitive else normalize_path(path).lower()
    include_patterns = [normalize_path(pattern) if case_sensitive else normalize_path(pattern).lower() for pattern in includes]
    exclude_patterns = [normalize_path(pattern) if case_sensitive else normalize_path(pattern).lower() for pattern in exclusions]
    if any(_glob_match_path(rule.rule_type, candidate_path, pattern) for pattern in exclude_patterns):
        return False
    return any(_glob_match_path(rule.rule_type, candidate_path, pattern) for pattern in include_patterns)


def _text_match(rule: RuleSnapshot, text: str) -> bool:
    includes, exclusions, issues = _pattern_parts(rule.pattern)
    if issues or not text:
        return False
    case_sensitive = _case_sensitive(rule)
    haystack = _compare_text(text, case_sensitive)
    if any((needle := _candidate_text(pattern, case_sensitive)) and needle in haystack for pattern in exclusions):
        return False
    return any((needle := _candidate_text(pattern, case_sensitive)) and needle in haystack for pattern in includes)


def _text_patterns_match(rule: RuleSnapshot, *values: str) -> bool:
    includes, exclusions, issues = _pattern_parts(rule.pattern)
    if issues:
        return False
    case_sensitive = _case_sensitive(rule)
    haystack = " ".join(_compare_text(value, case_sensitive) for value in values if value)
    if not haystack:
        return False
    if any((needle := _candidate_text(pattern, case_sensitive)) and needle in haystack for pattern in exclusions):
        return False
    return any((needle := _candidate_text(pattern, case_sensitive)) and needle in haystack for pattern in includes)


def _rule_matches(rule: RuleSnapshot, evidence: MappingEvidence) -> bool:
    if not _repository_applies(rule, evidence) or STATUS_WEIGHT.get(rule.status, 1.0) <= 0:
        return False
    if evidence.kind == "case_text":
        return rule.rule_type in CASE_TEXT_RULE_TYPES and _text_match(rule, evidence.text)

    case_sensitive = _case_sensitive(rule)
    path = evidence.path
    content = _compare_text(evidence.content, case_sensitive)
    structure_names = _compare_text(_structure_text(evidence.structures), case_sensitive)

    if rule.rule_type in PATH_RULE_TYPES and _path_match(rule, path):
        return True
    if rule.rule_type == "database_migration" and "database_migration" in _structure_types(evidence.structures):
        return True
    if rule.rule_type in {"api", "config_key"}:
        return _text_patterns_match(rule, structure_names, content)
    if rule.rule_type == "keyword":
        compare_path = _compare_text(normalize_path(path), case_sensitive)
        return _text_patterns_match(rule, compare_path, content)
    if rule.rule_type not in PATH_RULE_TYPES:
        compare_path = _compare_text(normalize_path(path), case_sensitive)
        return _text_patterns_match(rule, compare_path, content, structure_names)
    return False


def _fixed_prefix_length(pattern: str) -> int:
    match = re.search(r"[*?\[]", pattern)
    prefix = pattern[: match.start()] if match else pattern
    return len(normalize_path(prefix))


def _specificity(rule: RuleSnapshot) -> int:
    includes, _, _ = _pattern_parts(rule.pattern)
    pattern = max(includes, key=len, default="")
    wildcard_count = len(re.findall(r"[*?\[]", pattern))
    prefix_length = _fixed_prefix_length(pattern)
    if rule.rule_type == "file" and wildcard_count == 0:
        base = 1000
    elif rule.rule_type in {"file", "directory"}:
        base = 850
    elif rule.rule_type in PATH_RULE_TYPES:
        base = 700
    else:
        base = 300
    return base + min(prefix_length, 240) - wildcard_count * 25


def _score(rule: RuleSnapshot) -> int:
    return int(max(0, min(100, rule.confidence)) * RELATIONSHIP_WEIGHT.get(rule.relationship, 0.6) * STATUS_WEIGHT.get(rule.status, 1.0))


def _evidence_label(rule: RuleSnapshot) -> str:
    status_note = f", {rule.status}" if rule.status != "active" else ""
    return f"{rule.relationship} {rule.rule_type}:{rule.pattern}{status_note}"


def evaluate_mapping(evidence: MappingEvidence, rule_set: MappingRuleSet) -> MappingEvaluation:
    modules_by_id = rule_set.modules_by_id
    matches: list[MappingMatch] = []
    warnings: list[MappingIssue] = []
    conflicts: list[MappingIssue] = []

    for rule in rule_set.rules:
        if not _rule_matches(rule, evidence):
            continue
        match = MappingMatch(
            rule=rule,
            module=modules_by_id.get(rule.module_id),
            score=_score(rule),
            specificity=_specificity(rule),
            evidence=_evidence_label(rule),
        )
        matches.append(match)
        if rule.status == "stale":
            warnings.append(
                MappingIssue(
                    "warning",
                    "stale_rule_match",
                    "Matched a stale mapping rule; review the mapping before relying on it.",
                    rule_id=rule.id or None,
                    module_id=rule.module_id,
                    path=evidence.path or None,
                )
            )

    ownership_matches = [match for match in matches if match.score > 0]
    primary_modules = {match.rule.module_id for match in matches if match.rule.relationship == "primary" and match.score > 0}
    if len(primary_modules) > 1:
        conflicts.append(
            MappingIssue(
                "warning",
                "primary_conflict",
                "Multiple primary module rules matched the same evidence.",
                path=evidence.path or None,
            )
        )

    best_match: MappingMatch | None = None
    for match in ownership_matches:
        if best_match is None or (match.score, match.specificity) >= (best_match.score, best_match.specificity):
            best_match = match

    return MappingEvaluation(
        best_match=best_match,
        matches=tuple(matches),
        evidence=tuple(match.evidence for match in matches),
        warnings=tuple(warnings),
        primary_conflicts=tuple(conflicts),
    )


def _repository_scope_overlaps(left: RuleSnapshot, right: RuleSnapshot) -> bool:
    return left.repository_id is None or right.repository_id is None or left.repository_id == right.repository_id


def _patterns_may_overlap(left: RuleSnapshot, right: RuleSnapshot) -> bool:
    left_includes, _, _ = _pattern_parts(left.pattern)
    right_includes, _, _ = _pattern_parts(right.pattern)
    for left_pattern in left_includes:
        left_norm = normalize_path(left_pattern).rstrip("*").rstrip("/")
        for right_pattern in right_includes:
            right_norm = normalize_path(right_pattern).rstrip("*").rstrip("/")
            if not left_norm or not right_norm:
                continue
            if left_norm == right_norm or left_norm.startswith(right_norm + "/") or right_norm.startswith(left_norm + "/"):
                return True
    return False


def _is_test_path(path: str) -> bool:
    lowered = normalize_path(path).lower()
    return bool(re.search(r"(^|/)(test|tests|__tests__|spec|specs)(/|$)", lowered) or re.search(r"(^|/)(test_|.*_test|.*\.spec)\.", lowered))


def _risky_path_issues(candidate: RuleSnapshot, paths: list[str]) -> list[MappingIssue]:
    issues: list[MappingIssue] = []
    emitted: set[str] = set()
    for path in paths:
        lowered_parts = set(normalize_path(path).lower().split("/"))
        for segment, code in RISKY_PATH_SEGMENTS.items():
            if segment in lowered_parts and code not in emitted:
                emitted.add(code)
                issues.append(
                    MappingIssue(
                        "warning",
                        code,
                        "Sample inventory includes generated, dependency, or build-output paths; narrow the rule or add exclusions.",
                        module_id=candidate.module_id,
                        path=path,
                    )
                )
        if candidate.relationship == "primary" and _is_test_path(path) and "test_file_primary_match" not in emitted:
            emitted.add("test_file_primary_match")
            issues.append(
                MappingIssue(
                    "warning",
                    "test_file_primary_match",
                    "Primary rules that match test files should usually be narrowed or changed to evidence.",
                    module_id=candidate.module_id,
                    path=path,
                )
            )
    return issues


def preflight_rule(
    candidate_rule: RuleSnapshot,
    rule_set: MappingRuleSet,
    sample_inventory: Iterable[str] | None = None,
) -> RulePreflight:
    issues: list[MappingIssue] = []
    _, _, pattern_issues = _pattern_parts(candidate_rule.pattern)
    issues.extend(pattern_issues)

    for rule in rule_set.rules:
        if candidate_rule.id and rule.id == candidate_rule.id:
            continue
        if (
            rule.module_id == candidate_rule.module_id
            and rule.rule_type == candidate_rule.rule_type
            and normalize_path(rule.pattern) == normalize_path(candidate_rule.pattern)
        ):
            issues.append(
                MappingIssue(
                    "blocker",
                    "duplicate_rule",
                    "A mapping rule with this module, type, and pattern already exists.",
                    rule_id=rule.id or None,
                    module_id=rule.module_id,
                )
            )

    if candidate_rule.status == "stale" and not candidate_rule.stale_reason.strip():
        issues.append(
            MappingIssue(
                "warning",
                "stale_reason_missing",
                "Stale mapping rules should explain why they need review.",
                rule_id=candidate_rule.id or None,
                module_id=candidate_rule.module_id,
            )
        )

    if candidate_rule.rule_type in PATH_RULE_TYPES and candidate_rule.repository_id is None:
        issues.append(
            MappingIssue(
                "warning",
                "unscoped_path_rule",
                "Path-like rules should usually be scoped to a repository.",
                rule_id=candidate_rule.id or None,
                module_id=candidate_rule.module_id,
            )
        )

    if candidate_rule.relationship == "primary" and candidate_rule.rule_type in PATH_RULE_TYPES:
        for rule in rule_set.rules:
            if candidate_rule.id and rule.id == candidate_rule.id:
                continue
            if rule.relationship != "primary" or rule.rule_type not in PATH_RULE_TYPES or rule.module_id == candidate_rule.module_id:
                continue
            if _repository_scope_overlaps(candidate_rule, rule) and _patterns_may_overlap(candidate_rule, rule):
                issues.append(
                    MappingIssue(
                        "warning",
                        "primary_overlap",
                        "Another primary path rule may overlap this rule; review module ownership.",
                        rule_id=rule.id or None,
                        module_id=rule.module_id,
                    )
                )

    inventory = [normalize_path(path) for path in sample_inventory or [] if str(path).strip()]
    matched_paths = [path for path in inventory if _path_match(candidate_rule, path)]
    if matched_paths:
        issues.extend(_risky_path_issues(candidate_rule, matched_paths))
        if len(matched_paths) > 50 or len(matched_paths) > max(10, len(inventory) // 3):
            issues.append(
                MappingIssue(
                    "warning",
                    "broad_path_match",
                    "This rule matches a broad portion of the sampled repository inventory.",
                    module_id=candidate_rule.module_id,
                    path=matched_paths[0],
                )
            )
        if candidate_rule.relationship == "primary":
            for path in matched_paths[:20]:
                evidence = MappingEvidence(kind="repository_scan", repository_id=candidate_rule.repository_id, path=path)
                other_primary_modules = {
                    match.rule.module_id
                    for match in evaluate_mapping(evidence, rule_set).matches
                    if match.rule.relationship == "primary" and match.rule.module_id != candidate_rule.module_id
                }
                if other_primary_modules:
                    issues.append(
                        MappingIssue(
                            "warning",
                            "primary_sample_conflict",
                            "Sample inventory path also matches another primary module rule.",
                            module_id=next(iter(other_primary_modules)),
                            path=path,
                        )
                    )
                    break

    blocker_count = len([issue for issue in issues if issue.severity == "blocker"])
    warning_count = len([issue for issue in issues if issue.severity == "warning"])
    return RulePreflight(
        passed=blocker_count == 0,
        blocker_count=blocker_count,
        warning_count=warning_count,
        issues=tuple(issues),
        matched_sample_count=len(matched_paths),
        sample_paths=tuple(matched_paths[:10]),
    )
