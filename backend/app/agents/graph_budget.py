from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.config import AIInvocationLog
from app.agents import AgentRun, AgentToolCall
from app.agents.graph_types import AgentBudgetExceeded
from app.platform.config import Settings


class BudgetTracker:
    def __init__(self, *, db: Session, settings: Settings, run: AgentRun, requested_candidate_limit: int):
        self.db = db
        self.run = run
        self.started_at = time.monotonic()
        snapshot = dict(run.budget_snapshot or {})
        self.max_tool_calls = self._int_limit(
            snapshot, "max_tool_calls", settings.agent_default_max_tool_calls, settings.agent_system_max_tool_calls
        )
        self.max_subagents = self._int_limit(
            snapshot, "max_subagents", settings.agent_default_max_subagents, settings.agent_system_max_subagents
        )
        self.max_parallel_subagents = self._int_limit(
            snapshot,
            "max_parallel_subagents",
            settings.agent_default_max_parallel_subagents,
            settings.agent_system_max_parallel_subagents,
        )
        self.max_model_calls = self._int_limit(
            snapshot, "max_model_calls", settings.agent_default_max_model_calls, settings.agent_system_max_model_calls
        )
        self.max_case_candidates = self._int_limit(
            snapshot,
            "max_case_candidates_per_run",
            min(settings.agent_default_max_case_candidates_per_run, requested_candidate_limit),
            settings.agent_system_max_case_candidates_per_run,
        )
        self.max_wall_time_seconds = (
            self._int_limit(
                snapshot,
                "max_wall_time_minutes",
                settings.agent_default_max_wall_time_minutes,
                settings.agent_system_max_wall_time_minutes,
            )
            * 60
        )
        self.max_total_source_chars_sent = self._int_limit(
            snapshot,
            "max_total_source_chars_sent",
            settings.agent_default_max_total_source_chars_sent,
            settings.agent_system_max_total_source_chars_sent,
        )
        self.requested_candidate_limit = requested_candidate_limit
        self.tool_calls = len(
            db.scalars(select(AgentToolCall).where(AgentToolCall.agent_run_id == run.id)).all()
        )
        self.model_calls = len(
            db.scalars(select(AIInvocationLog).where(AIInvocationLog.agent_run_id == run.id)).all()
        )
        self.subagents = int((snapshot.get("usage") or {}).get("subagents") or 0)
        self.parallel_subagents = int((snapshot.get("usage") or {}).get("parallel_subagents") or 0)
        self.candidates = 0
        self.source_chars_sent = int((snapshot.get("usage") or {}).get("source_chars_sent") or 0)
        if requested_candidate_limit > self.max_case_candidates:
            raise AgentBudgetExceeded(
                f"candidate budget exceeded: requested {requested_candidate_limit}, limit {self.max_case_candidates}"
            )
        self._write_usage()

    @staticmethod
    def _int_limit(snapshot: dict[str, Any], key: str, default: int, hard_cap: int) -> int:
        try:
            value = max(0, int(snapshot.get(key, default)))
        except (TypeError, ValueError):
            value = default
        return min(value, hard_cap)

    @property
    def effective_candidate_limit(self) -> int:
        return min(self.requested_candidate_limit, self.max_case_candidates)

    def check_tool(self, tool_name: str, cost: int) -> None:
        self.check_wall_time()
        if self.tool_calls + cost > self.max_tool_calls:
            raise AgentBudgetExceeded(
                f"tool budget exceeded before {tool_name}: used {self.tool_calls}, cost {cost}, limit {self.max_tool_calls}"
            )
        self.tool_calls += cost
        self._write_usage()

    def check_model(self) -> None:
        self.check_wall_time()
        if self.model_calls + 1 > self.max_model_calls:
            raise AgentBudgetExceeded(
                f"model budget exceeded before candidate generation: used {self.model_calls}, limit {self.max_model_calls}"
            )
        self.model_calls += 1
        self._write_usage()

    def check_subagents(self, names: list[str], parallel_group_size: int = 1) -> None:
        self.check_wall_time()
        count = len([name for name in names if name])
        if self.subagents + count > self.max_subagents:
            raise AgentBudgetExceeded(
                f"subagent budget exceeded: used {self.subagents}, requested {count}, limit {self.max_subagents}"
            )
        parallel_count = max(1, parallel_group_size)
        if parallel_count > self.max_parallel_subagents:
            raise AgentBudgetExceeded(
                f"parallel subagent budget exceeded: requested {parallel_count}, limit {self.max_parallel_subagents}"
            )
        self.subagents += count
        self.parallel_subagents = max(self.parallel_subagents, parallel_count)
        self._write_usage()

    def check_candidates(self, count: int) -> None:
        self.check_wall_time()
        if count > self.effective_candidate_limit:
            raise AgentBudgetExceeded(
                f"candidate budget exceeded: model returned {count}, limit {self.effective_candidate_limit}"
            )
        self.candidates = count
        self._write_usage()

    def check_wall_time(self) -> None:
        elapsed = int(time.monotonic() - self.started_at)
        if elapsed > self.max_wall_time_seconds:
            raise AgentBudgetExceeded(
                f"wall-clock budget exceeded: used {elapsed}s, limit {self.max_wall_time_seconds}s"
            )

    def add_source_chars(self, count: int) -> None:
        self.check_wall_time()
        next_count = self.source_chars_sent + max(0, count)
        if next_count > self.max_total_source_chars_sent:
            raise AgentBudgetExceeded(
                f"source context budget exceeded: requested {next_count} chars, limit {self.max_total_source_chars_sent}"
            )
        self.source_chars_sent = next_count
        self._write_usage()

    def _write_usage(self) -> None:
        snapshot = dict(self.run.budget_snapshot or {})
        snapshot["usage"] = {
            "tool_calls": self.tool_calls,
            "subagents": self.subagents,
            "parallel_subagents": self.parallel_subagents,
            "model_calls": self.model_calls,
            "case_candidates": self.candidates,
            "source_chars_sent": self.source_chars_sent,
            "wall_time_seconds": int(time.monotonic() - self.started_at),
        }
        snapshot["limits"] = {
            "max_tool_calls": self.max_tool_calls,
            "max_subagents": self.max_subagents,
            "max_parallel_subagents": self.max_parallel_subagents,
            "max_model_calls": self.max_model_calls,
            "max_case_candidates_per_run": self.max_case_candidates,
            "max_wall_time_minutes": self.max_wall_time_seconds // 60,
            "max_total_source_chars_sent": self.max_total_source_chars_sent,
        }
        self.run.budget_snapshot = snapshot
        self.db.flush()


