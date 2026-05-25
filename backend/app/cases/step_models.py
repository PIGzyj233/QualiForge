"""Shared shape for a test case step with its expected result."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class CaseStep(BaseModel):
    """One step in a test case, paired with the expected outcome of that step."""

    action: str = Field(min_length=1, max_length=1000)
    expected: str = Field(default="", max_length=1000)


def normalize_steps_payload(value: Any) -> list[dict[str, str]]:
    """Coerce inbound `steps` payloads into the canonical [{action, expected}] shape.

    Accepts:
    - list[CaseStep]
    - list[dict] with `action`/`expected` keys
    - list[str] (legacy, expected becomes empty)
    - None / empty (returns [])
    """
    if not value:
        return []
    out: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, CaseStep):
            out.append({"action": item.action.strip(), "expected": item.expected.strip()})
            continue
        if isinstance(item, dict):
            action = str(item.get("action") or "").strip()
            expected = str(item.get("expected") or "").strip()
            if action:
                out.append({"action": action, "expected": expected})
            continue
        if isinstance(item, str):
            action = item.strip()
            if action:
                out.append({"action": action, "expected": ""})
            continue
    return out


def fold_legacy_expected(steps: list[dict[str, str]], expected_result: str | None) -> list[dict[str, str]]:
    """If incoming data has a single overall expected_result and steps lack expectations,
    attach it to the last step so legacy CSV imports remain useful."""
    if not expected_result:
        return steps
    cleaned = expected_result.strip()
    if not cleaned or not steps:
        return steps
    if any(step.get("expected") for step in steps):
        return steps
    steps[-1]["expected"] = cleaned
    return steps


def stringify_steps(steps: list[Any]) -> list[str]:
    """Compatibility: legacy callers that only know list[str]. Used in tests for assertions."""
    out: list[str] = []
    for item in steps:
        if isinstance(item, dict):
            action = item.get("action") or ""
            expected = item.get("expected") or ""
            out.append(f"{action} -> {expected}" if expected else action)
        else:
            out.append(str(item))
    return out


class StepValidatorMixin:
    """Pydantic mixin that auto-normalizes `steps` and folds legacy `expected_result`."""

    @field_validator("steps", mode="before")
    @classmethod
    def _normalize_steps(cls, value: Any) -> Any:
        return normalize_steps_payload(value)
