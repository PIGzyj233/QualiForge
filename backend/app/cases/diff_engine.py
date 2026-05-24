from __future__ import annotations

import fnmatch
import re
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cases.diff_models import ChangeType, DiffAnalysis, DiffAnalysisResponse, DiffAnalysisStatus, RiskLevel
from app.cases.modules import ModuleMappingRule, ProjectModule
from app.git.models import GitRepository, Job, JobStatus
from app.git.sandbox import ensure_safe_sandbox_path, run_git
from app.workspace.routes import now_utc


RISK_ORDER = {RiskLevel.low.value: 1, RiskLevel.medium.value: 2, RiskLevel.high.value: 3}


def analysis_to_response(analysis: DiffAnalysis) -> DiffAnalysisResponse:
    return DiffAnalysisResponse(
        id=analysis.id,
        workspace_id=analysis.workspace_id,
        project_id=analysis.project_id,
        repository_id=analysis.repository_id,
        job_id=analysis.job_id,
        base_ref=analysis.base_ref,
        target_ref=analysis.target_ref,
        status=analysis.status,
        risk_level=analysis.risk_level,
        summary=analysis.summary,
        recommended_scope=analysis.recommended_scope,
        file_changes=analysis.file_changes,
        module_impacts=analysis.module_impacts,
        key_logs=analysis.key_logs,
        error_summary=analysis.error_summary,
        created_by=analysis.created_by,
        created_at=analysis.created_at,
        completed_at=analysis.completed_at,
    )


def max_risk(*levels: str) -> str:
    return max(levels or (RiskLevel.low.value,), key=lambda item: RISK_ORDER.get(item, 0))


def normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def detect_language(path: str) -> str:
    extension = Path(path).suffix.lower()
    return {
        ".py": "Python",
        ".ts": "TypeScript",
        ".tsx": "TypeScript React",
        ".js": "JavaScript",
        ".jsx": "JavaScript React",
        ".go": "Go",
        ".java": "Java",
        ".kt": "Kotlin",
        ".rb": "Ruby",
        ".php": "PHP",
        ".cs": "C#",
        ".sql": "SQL",
        ".yaml": "YAML",
        ".yml": "YAML",
        ".json": "JSON",
        ".toml": "TOML",
        ".ini": "INI",
        ".env": "ENV",
        ".md": "Markdown",
    }.get(extension, extension.lstrip(".").upper() or "Unknown")


def is_test_path(path: str) -> bool:
    lowered = normalize_path(path).lower()
    name = Path(lowered).name
    return "/test/" in lowered or "/tests/" in lowered or name.startswith("test_") or name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))


def is_migration_path(path: str) -> bool:
    lowered = normalize_path(path).lower()
    return lowered.endswith(".sql") or "/migration" in lowered or "/migrations/" in lowered


def read_worktree_file(worktree_path: Path, relative_path: str) -> str:
    file_path = (worktree_path / normalize_path(relative_path)).resolve(strict=False)
    root = worktree_path.resolve(strict=False)
    if root != file_path and root not in file_path.parents:
        return ""
    if not file_path.exists() or not file_path.is_file():
        return ""
    try:
        return file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def read_git_file(worktree_path: Path, ref_sha: str, relative_path: str, timeout_seconds: int, key_logs: list[str]) -> str:
    result = run_git(["git", "-C", str(worktree_path), "show", f"{ref_sha}:{normalize_path(relative_path)}"], timeout_seconds, key_logs)
    if result.returncode != 0:
        return ""
    return result.stdout


def named_matches(pattern: str, content: str) -> set[str]:
    return {match.group(1) for match in re.finditer(pattern, content, re.MULTILINE)}


def classify_named_changes(kind: str, base_names: set[str], target_names: set[str]) -> list[dict[str, str]]:
    changes: list[dict[str, str]] = []
    for name in sorted(target_names - base_names):
        changes.append({"type": kind, "name": name, "state": "added"})
    for name in sorted(base_names - target_names):
        changes.append({"type": kind, "name": name, "state": "removed"})
    for name in sorted(base_names & target_names)[:8]:
        changes.append({"type": kind, "name": name, "state": "present"})
    return changes


def detect_structure(path: str, base_content: str, target_content: str) -> list[dict[str, str]]:
    content = target_content or base_content
    lowered_path = normalize_path(path).lower()
    structures: list[dict[str, str]] = []
    structures.extend(
        classify_named_changes(
            "function",
            named_matches(r"^\s*(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", base_content)
            | named_matches(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", base_content)
            | named_matches(r"^\s*(?:export\s+)?const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s*)?\(", base_content),
            named_matches(r"^\s*(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", target_content)
            | named_matches(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", target_content)
            | named_matches(r"^\s*(?:export\s+)?const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s*)?\(", target_content),
        )
    )
    structures.extend(
        classify_named_changes(
            "class",
            named_matches(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)", base_content),
            named_matches(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)", target_content),
        )
    )

    route_patterns = [
        r"@\w+\.(?:get|post|put|patch|delete)\(\s*[\"']([^\"']+)",
        r"\b(?:app|router)\.(?:get|post|put|patch|delete)\(\s*[\"']([^\"']+)",
    ]
    base_routes: set[str] = set()
    target_routes: set[str] = set()
    for pattern in route_patterns:
        base_routes |= named_matches(pattern, base_content)
        target_routes |= named_matches(pattern, target_content)
    structures.extend(classify_named_changes("api_route", base_routes, target_routes))

    if is_migration_path(path):
        sql_signals = [
            match.group(0).strip()[:120]
            for match in re.finditer(r"(?im)^\s*(create|alter|drop)\s+(table|index|view|column)[^;]*", content)
        ]
        structures.append(
            {
                "type": "database_migration",
                "name": Path(path).name,
                "state": "present",
                "evidence": ", ".join(sql_signals[:3]) or "migration file changed",
            }
        )

    if Path(lowered_path).suffix in {".env", ".yaml", ".yml", ".json", ".toml", ".ini"} or "config" in lowered_path:
        config_names = set(re.findall(r"(?m)^\s*([A-Za-z_][A-Za-z0-9_.-]{1,80})\s*[:=]", content))
        config_names |= set(re.findall(r'"([A-Za-z_][A-Za-z0-9_.-]{1,80})"\s*:', content))
        for name in sorted(config_names)[:10]:
            structures.append({"type": "config_key", "name": name, "state": "present"})

    if is_test_path(path):
        structures.append({"type": "test_file", "name": Path(path).name, "state": "present"})

    return structures[:30]


def parse_name_status(output: str) -> list[dict[str, str | None]]:
    changes: list[dict[str, str | None]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status_code = parts[0]
        if status_code.startswith("R") and len(parts) >= 3:
            changes.append({"change_type": ChangeType.renamed.value, "old_path": normalize_path(parts[1]), "path": normalize_path(parts[2])})
        elif status_code == "A" and len(parts) >= 2:
            changes.append({"change_type": ChangeType.added.value, "old_path": None, "path": normalize_path(parts[1])})
        elif status_code == "D" and len(parts) >= 2:
            changes.append({"change_type": ChangeType.deleted.value, "old_path": None, "path": normalize_path(parts[1])})
        else:
            changes.append({"change_type": ChangeType.modified.value, "old_path": None, "path": normalize_path(parts[-1])})
    return changes


def parse_numstat(output: str) -> dict[str, dict[str, int]]:
    stats: dict[str, dict[str, int]] = {}
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        additions = 0 if parts[0] == "-" else int(parts[0])
        deletions = 0 if parts[1] == "-" else int(parts[1])
        stats[normalize_path(parts[-1])] = {"additions": additions, "deletions": deletions}
    return stats


def load_modules_and_rules(db: Session, workspace_id: str, project_id: str) -> tuple[list[ProjectModule], list[ModuleMappingRule]]:
    modules = db.scalars(
        select(ProjectModule)
        .where(ProjectModule.workspace_id == workspace_id, ProjectModule.project_id == project_id)
        .order_by(ProjectModule.path)
    ).all()
    rules = db.scalars(
        select(ModuleMappingRule)
        .where(ModuleMappingRule.workspace_id == workspace_id, ModuleMappingRule.project_id == project_id)
        .order_by(ModuleMappingRule.confidence.desc(), ModuleMappingRule.rule_type)
    ).all()
    return list(modules), list(rules)


def match_module(
    path: str,
    content: str,
    structures: list[dict[str, str]],
    modules_by_id: dict[str, ProjectModule],
    rules: list[ModuleMappingRule],
) -> tuple[ProjectModule | None, int, list[str]]:
    normalized = normalize_path(path).lower()
    content_lower = content.lower()
    structure_names = " ".join(str(item.get("name", "")) for item in structures).lower()
    best_module: ProjectModule | None = None
    best_confidence = 0
    evidence: list[str] = []

    for rule in rules:
        pattern = normalize_path(rule.pattern).lower()
        matched = False
        if rule.rule_type == "directory":
            matched = normalized.startswith(pattern.rstrip("/") + "/") or normalized == pattern.rstrip("/")
        elif rule.rule_type == "file":
            matched = fnmatch.fnmatch(normalized, pattern) or normalized.endswith(pattern)
        elif rule.rule_type == "api":
            matched = pattern in structure_names or pattern in content_lower
        elif rule.rule_type == "service":
            matched = pattern in normalized or pattern in content_lower
        elif rule.rule_type == "config_key":
            matched = pattern in structure_names or pattern in content_lower
        elif rule.rule_type == "database_migration":
            matched = pattern in normalized or any(item.get("type") == "database_migration" for item in structures)
        elif rule.rule_type == "keyword":
            matched = pattern in normalized or pattern in content_lower

        if matched and rule.confidence >= best_confidence:
            best_module = modules_by_id.get(rule.module_id)
            best_confidence = rule.confidence
            evidence = [f"{rule.rule_type}:{rule.pattern}"]

    return best_module, best_confidence, evidence


def file_risk(change_type: str, path: str, structures: list[dict[str, str]], additions: int, deletions: int) -> str:
    structure_types = {item.get("type") for item in structures}
    if (
        change_type in {ChangeType.deleted.value, ChangeType.renamed.value}
        or is_migration_path(path)
        or {"api_route", "config_key", "database_migration"} & structure_types
    ):
        return RiskLevel.high.value
    if {"function", "class"} & structure_types or additions + deletions > 120:
        return RiskLevel.medium.value
    return RiskLevel.low.value


def impact_recommendations(risk_level: str, module_key: str) -> list[str]:
    if risk_level == RiskLevel.high.value:
        return [
            f"Run full regression for {module_key}",
            "Prioritize API, config, migration, and rollback checks",
            "Review approved cases linked to the impacted module before release",
        ]
    if risk_level == RiskLevel.medium.value:
        return [
            f"Run focused functional tests for {module_key}",
            "Cover changed functions/classes and adjacent happy-path cases",
        ]
    return [f"Run smoke tests for {module_key}", "Review changed evidence files for missed mapping rules"]


def build_module_impacts(file_changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in file_changes:
        key = str(item.get("module_id") or "UNMAPPED")
        grouped[key].append(item)

    impacts: list[dict[str, Any]] = []
    for module_id, files in grouped.items():
        risk = max_risk(*(str(item["risk_level"]) for item in files))
        confidence_values = [int(item.get("confidence") or 0) for item in files if item.get("confidence")]
        confidence = int(sum(confidence_values) / len(confidence_values)) if confidence_values else 55
        module_key = str(files[0].get("module_key") or "UNMAPPED")
        evidence: list[str] = []
        for item in files[:6]:
            structure_bits = ", ".join(f"{entry.get('type')}:{entry.get('name')}" for entry in item.get("structure_changes", [])[:3])
            evidence.append(f"{item['path']} ({item['change_type']}, {structure_bits or item['language']})")

        impacts.append(
            {
                "module_id": None if module_id == "UNMAPPED" else module_id,
                "module_key": module_key,
                "module_name": files[0].get("module_name") or "Unmapped",
                "risk_level": risk,
                "changed_file_count": len(files),
                "recommended_tests": impact_recommendations(risk, module_key),
                "evidence": evidence,
                "confidence": confidence,
            }
        )

    return sorted(impacts, key=lambda item: (-RISK_ORDER.get(str(item["risk_level"]), 0), str(item["module_key"])))


def build_recommended_scope(module_impacts: list[dict[str, Any]], file_changes: list[dict[str, Any]]) -> list[str]:
    scope: list[str] = []
    for impact in module_impacts:
        scope.extend(str(item) for item in impact["recommended_tests"])
    if any(item.get("is_test_file") for item in file_changes):
        scope.append("Review changed automated tests as supporting evidence, not as the only release signal")
    return list(dict.fromkeys(scope))[:12]


def run_analysis(
    *,
    db: Session,
    settings_root: Path,
    repository: GitRepository,
    analysis: DiffAnalysis,
    job: Job,
) -> None:
    key_logs = [f"Diff analysis started for {repository.name}", f"Sandbox root: {settings_root}"]
    root = settings_root.expanduser()
    mirror_path = ensure_safe_sandbox_path(root, Path(repository.mirror_path))
    if not mirror_path.exists():
        raise RuntimeError("Repository mirror does not exist; sync repository first")

    base_result = run_git(["git", "--git-dir", str(mirror_path), "rev-parse", "--verify", f"{analysis.base_ref}^{{commit}}"], repository.sync_timeout_seconds, key_logs)
    target_result = run_git(["git", "--git-dir", str(mirror_path), "rev-parse", "--verify", f"{analysis.target_ref}^{{commit}}"], repository.sync_timeout_seconds, key_logs)
    if base_result.returncode != 0:
        raise RuntimeError(f"Base ref not found: {analysis.base_ref}")
    if target_result.returncode != 0:
        raise RuntimeError(f"Target ref not found: {analysis.target_ref}")
    base_sha = base_result.stdout.strip()
    target_sha = target_result.stdout.strip()

    worktree_path = ensure_safe_sandbox_path(root, root / analysis.workspace_id[:12] / analysis.project_id[:12] / "diff-worktrees" / analysis.id[:12])
    if worktree_path.exists():
        shutil.rmtree(worktree_path)
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        clone = run_git(["git", "clone", "--shared", "--no-checkout", "--", str(mirror_path), str(worktree_path)], repository.sync_timeout_seconds, key_logs)
        if clone.returncode != 0:
            raise RuntimeError(clone.stderr.strip()[:500] or "Failed to create temporary worktree")
        checkout = run_git(["git", "-C", str(worktree_path), "checkout", "--detach", target_sha], repository.sync_timeout_seconds, key_logs)
        if checkout.returncode != 0:
            raise RuntimeError(checkout.stderr.strip()[:500] or "Failed to checkout target ref")

        name_status = run_git(["git", "-C", str(worktree_path), "diff", "--name-status", "-M", base_sha, target_sha, "--"], repository.sync_timeout_seconds, key_logs)
        if name_status.returncode != 0:
            raise RuntimeError(name_status.stderr.strip()[:500] or "Git diff failed")
        raw_changes = parse_name_status(name_status.stdout)
        if len(raw_changes) > repository.diff_file_limit:
            raise RuntimeError(f"Diff changes {len(raw_changes)} files, above limit {repository.diff_file_limit}")

        numstat = run_git(["git", "-C", str(worktree_path), "diff", "--numstat", "-M", base_sha, target_sha, "--"], repository.sync_timeout_seconds, key_logs)
        stats = parse_numstat(numstat.stdout) if numstat.returncode == 0 else {}

        modules, rules = load_modules_and_rules(db, repository.workspace_id, repository.project_id)
        modules_by_id = {module.id: module for module in modules}
        file_changes: list[dict[str, Any]] = []
        for raw in raw_changes:
            path = str(raw["path"])
            old_path = str(raw["old_path"]) if raw.get("old_path") else None
            change_type = str(raw["change_type"])
            target_content = "" if change_type == ChangeType.deleted.value else read_worktree_file(worktree_path, path)
            base_content = read_git_file(worktree_path, base_sha, old_path or path, repository.sync_timeout_seconds, key_logs)
            structures = detect_structure(path, base_content, target_content)
            module, confidence, match_evidence = match_module(path, target_content or base_content, structures, modules_by_id, rules)
            stat = stats.get(path, {"additions": 0, "deletions": 0})
            risk = file_risk(change_type, path, structures, int(stat["additions"]), int(stat["deletions"]))

            file_changes.append(
                {
                    "path": path,
                    "old_path": old_path,
                    "directory": str(Path(path).parent).replace("\\", "/") if str(Path(path).parent) != "." else ".",
                    "language": detect_language(path),
                    "change_type": change_type,
                    "additions": stat["additions"],
                    "deletions": stat["deletions"],
                    "module_id": module.id if module else None,
                    "module_key": (module.code or module.slug.upper().replace("-", "_")) if module else None,
                    "module_name": module.name if module else None,
                    "is_test_file": is_test_path(path),
                    "is_migration": is_migration_path(path),
                    "structure_changes": structures,
                    "risk_level": risk,
                    "confidence": confidence or 55,
                    "evidence": match_evidence or [f"{detect_language(path)} {change_type}"],
                }
            )

        module_impacts = build_module_impacts(file_changes)
        risk = max_risk(*(str(item["risk_level"]) for item in file_changes))
        recommended_scope = build_recommended_scope(module_impacts, file_changes)
        analysis.status = DiffAnalysisStatus.succeeded.value
        analysis.risk_level = risk
        analysis.file_changes = file_changes
        analysis.module_impacts = module_impacts
        analysis.recommended_scope = recommended_scope
        analysis.summary = f"{len(file_changes)} files changed across {len(module_impacts)} module groups; overall risk {risk}"
        analysis.key_logs = [*key_logs, f"Temporary worktree: {worktree_path}", analysis.summary]
        job.status = JobStatus.succeeded.value
        job.output_summary = analysis.summary
        job.key_logs = analysis.key_logs
    finally:
        if worktree_path.exists():
            shutil.rmtree(worktree_path)


def get_analysis_or_404(db: Session, workspace_id: str, project_id: str, analysis_id: str) -> DiffAnalysis:
    analysis = db.scalar(
        select(DiffAnalysis).where(
            DiffAnalysis.id == analysis_id,
            DiffAnalysis.workspace_id == workspace_id,
            DiffAnalysis.project_id == project_id,
        )
    )
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diff analysis not found")
    return analysis
