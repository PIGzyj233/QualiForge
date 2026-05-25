"""Shared shape for a test case step with its expected result."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


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
    if isinstance(value, str):
        value = [value]
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


def normalize_steps_with_legacy(value: Any, expected_result: str | None = None) -> list[dict[str, str]]:
    """Normalize canonical or legacy step payloads and preserve legacy expected text."""
    return fold_legacy_expected(normalize_steps_payload(value), expected_result)


def steps_expected_text(steps: Any) -> str:
    """Return all step-level expected results as a compact legacy-compatible string."""
    normalized = normalize_steps_payload(steps)
    return "\n".join(step["expected"] for step in normalized if step.get("expected"))


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

    @model_validator(mode="before")
    @classmethod
    def _normalize_step_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "steps" in data:
            data["steps"] = normalize_steps_with_legacy(
                data.get("steps"),
                str(data.get("expected_result") or "") or None,
            )
        return data
