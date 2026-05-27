from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.git.code_tools import (
    CodeToolError,
    code_read_numbered_range,
    code_read_range,
    code_rg_files,
    code_search,
    git_diff,
    git_show_file,
    git_status,
)


def run(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)


def create_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    run(["git", "init"], repo)
    run(["git", "config", "user.email", "tester@qualiforge.local"], repo)
    run(["git", "config", "user.name", "QualiForge Tester"], repo)
    app_dir = repo / "backend" / "app"
    app_dir.mkdir(parents=True)
    (app_dir / "checkout.py").write_text(
        "def create_order():\n"
        "    return 'created'\n"
        "\n"
        "def refund_order(order_id):\n"
        "    audit_event = 'refund.created'\n"
        "    return audit_event\n",
        encoding="utf-8",
    )
    run(["git", "add", "."], repo)
    run(["git", "commit", "-m", "initial"], repo)
    (app_dir / "checkout.py").write_text(
        "def create_order():\n"
        "    return 'created'\n"
        "\n"
        "def refund_order(order_id):\n"
        "    audit_event = 'refund.created'\n"
        "    logger_key = 'refund_id'\n"
        "    return audit_event\n",
        encoding="utf-8",
    )
    return repo


def test_code_reader_toolbox_lists_searches_and_reads_ranges(tmp_path: Path) -> None:
    repo = create_repo(tmp_path)

    files = code_rg_files(repo, path="backend", glob="*.py")
    assert files == ["backend/app/checkout.py"]

    matches = code_search(repo, pattern="refund", path="backend/app", max_results=5)
    assert matches[0].path == "backend/app/checkout.py"
    assert matches[0].line == 4
    assert "refund_order" in matches[0].text

    read = code_read_range(repo, path="backend/app/checkout.py", start_line=4, end_line=6)
    assert read.content == "def refund_order(order_id):\n    audit_event = 'refund.created'\n    logger_key = 'refund_id'"

    numbered = code_read_numbered_range(repo, path="backend/app/checkout.py", start_line=4, end_line=5)
    assert "4 def refund_order(order_id):" in numbered.content
    assert "5     audit_event = 'refund.created'" in numbered.content


def test_code_reader_toolbox_git_read_operations_are_read_only(tmp_path: Path) -> None:
    repo = create_repo(tmp_path)

    status = git_status(repo)
    assert "M backend/app/checkout.py" in status

    diff = git_diff(repo, path="backend/app/checkout.py")
    assert "+    logger_key = 'refund_id'" in diff

    original = git_show_file(repo, ref="HEAD", path="backend/app/checkout.py")
    assert "logger_key" not in original.content
    assert "refund.created" in original.content


def test_code_reader_toolbox_rejects_path_escape(tmp_path: Path) -> None:
    repo = create_repo(tmp_path)

    with pytest.raises(CodeToolError, match="escapes"):
        code_read_range(repo, path="../outside.py", start_line=1, end_line=1)

    with pytest.raises(CodeToolError, match="escapes"):
        git_diff(repo, path="../outside.py")
