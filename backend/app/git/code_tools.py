from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class CodeToolError(Exception):
    """Raised when a typed code-reading tool cannot safely complete."""


@dataclass(frozen=True)
class CodeSearchMatch:
    path: str
    line: int
    column: int
    text: str


@dataclass(frozen=True)
class CodeReadResult:
    path: str
    start_line: int
    end_line: int
    content: str


def resolve_sandbox_path(root: Path, relative_path: str = ".") -> Path:
    sandbox_root = root.resolve(strict=False)
    candidate = (sandbox_root / relative_path).resolve(strict=False)
    if candidate != sandbox_root and sandbox_root not in candidate.parents:
        raise CodeToolError("Path escapes the code sandbox")
    return candidate


def _relative(root: Path, path: Path) -> str:
    return path.resolve(strict=False).relative_to(root.resolve(strict=False)).as_posix()


def _normalize_tool_path(path: str) -> str:
    return path.replace("\\", "/")


def _run_read_command(command: list[str], *, cwd: Path, timeout_seconds: int = 10) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CodeToolError("Code read command timed out") from exc
    if result.returncode not in {0, 1}:
        detail = (result.stderr or result.stdout).strip()[:500]
        raise CodeToolError(detail or f"Code read command failed with exit code {result.returncode}")
    return result


def _run_git_probe(command: list[str], *, cwd: Path, timeout_seconds: int = 10) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CodeToolError("Code read command timed out") from exc


def code_rg_files(root: Path, *, path: str = ".", glob: str | None = None, max_results: int = 500) -> list[str]:
    sandbox_root = root.resolve(strict=False)
    search_path = resolve_sandbox_path(sandbox_root, path)
    command = ["rg", "--files"]
    if glob:
        command.extend(["-g", glob])
    command.append(_relative(sandbox_root, search_path))
    result = _run_read_command(command, cwd=sandbox_root)
    return [_normalize_tool_path(line) for line in result.stdout.splitlines() if line][:max_results]


def code_search(
    root: Path,
    *,
    pattern: str,
    path: str = ".",
    case_sensitive: bool = False,
    max_results: int = 100,
) -> list[CodeSearchMatch]:
    sandbox_root = root.resolve(strict=False)
    search_path = resolve_sandbox_path(sandbox_root, path)
    command = ["rg", "-n", "--column", "--no-heading", "--color", "never"]
    if not case_sensitive:
        command.append("-i")
    command.extend(["--", pattern, _relative(sandbox_root, search_path)])
    result = _run_read_command(command, cwd=sandbox_root)
    matches: list[CodeSearchMatch] = []
    for line in result.stdout.splitlines():
        if len(matches) >= max_results:
            break
        parts = line.split(":", 3)
        if len(parts) != 4:
            continue
        file_path, line_no, column_no, text = parts
        try:
            matches.append(CodeSearchMatch(path=_normalize_tool_path(file_path), line=int(line_no), column=int(column_no), text=text))
        except ValueError:
            continue
    return matches


def code_read_range(root: Path, *, path: str, start_line: int, end_line: int, numbered: bool = False) -> CodeReadResult:
    if start_line < 1 or end_line < start_line:
        raise CodeToolError("Invalid line range")
    file_path = resolve_sandbox_path(root, path)
    sandbox_root = root.resolve(strict=False)
    if not file_path.is_file():
        raise CodeToolError("Code file not found")
    lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    selected = lines[start_line - 1 : end_line]
    if numbered:
        width = len(str(end_line))
        content = "\n".join(f"{index:>{width}} {line}" for index, line in enumerate(selected, start=start_line))
    else:
        content = "\n".join(selected)
    return CodeReadResult(
        path=_relative(sandbox_root, file_path),
        start_line=start_line,
        end_line=min(end_line, len(lines)),
        content=content,
    )


def code_read_numbered_range(root: Path, *, path: str, start_line: int, end_line: int) -> CodeReadResult:
    return code_read_range(root, path=path, start_line=start_line, end_line=end_line, numbered=True)


def git_status(root: Path) -> str:
    sandbox_root = root.resolve(strict=False)
    result = _run_read_command(["git", "status", "--short"], cwd=sandbox_root)
    return result.stdout


def git_diff(root: Path, *, base_ref: str | None = None, target_ref: str | None = None, path: str | None = None) -> str:
    sandbox_root = root.resolve(strict=False)
    command = ["git", "diff"]
    if base_ref and target_ref:
        command.append(f"{base_ref}..{target_ref}")
    if path:
        safe_path = resolve_sandbox_path(sandbox_root, path)
        command.extend(["--", _relative(sandbox_root, safe_path)])
    result = _run_read_command(command, cwd=sandbox_root)
    return result.stdout


def git_show_file(root: Path, *, ref: str, path: str) -> CodeReadResult:
    sandbox_root = root.resolve(strict=False)
    safe_path = resolve_sandbox_path(sandbox_root, path)
    relative_path = _relative(sandbox_root, safe_path)
    try:
        result = _run_read_command(["git", "show", f"{ref}:{relative_path}"], cwd=sandbox_root)
    except CodeToolError as exc:
        fallback = _read_clean_worktree_file_at_ref(sandbox_root, safe_path, ref, relative_path)
        if fallback is None:
            raise exc
        return fallback
    content = result.stdout.rstrip("\n")
    return CodeReadResult(
        path=relative_path,
        start_line=1,
        end_line=len(content.splitlines()),
        content=content,
    )


def _read_clean_worktree_file_at_ref(sandbox_root: Path, safe_path: Path, ref: str, relative_path: str) -> CodeReadResult | None:
    resolved = _run_git_probe(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=sandbox_root)
    head = _run_git_probe(["git", "rev-parse", "--verify", "HEAD^{commit}"], cwd=sandbox_root)
    if resolved.returncode != 0 or head.returncode != 0 or resolved.stdout.strip() != head.stdout.strip():
        return None
    status = _run_git_probe(["git", "status", "--porcelain", "--", relative_path], cwd=sandbox_root)
    if status.returncode != 0 or status.stdout.strip():
        return None
    if not safe_path.is_file():
        return None
    content = safe_path.read_text(encoding="utf-8", errors="ignore").rstrip("\n")
    return CodeReadResult(
        path=relative_path,
        start_line=1,
        end_line=len(content.splitlines()),
        content=content,
    )
