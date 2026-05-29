from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.agents.coverage import classify_candidate_coverage, lookup_coverage_records, transition_staged_output_coverage
from app.agents.graph_types import GeneratedCaseCandidate
from app.agents.models import AgentRun, AgentStagedOutput, AgentStagedOutputStatus, AgentStagedOutputType, CoverageIndexEntry
from app.cases.ai_suggestions import AISuggestion, AISuggestionStatus, AISuggestionType
from app.cases.diff_models import DiffAnalysis, DiffAnalysisStatus
from app.cases.domain import CaseRevision, TestCase as CaseModel, TestCaseLifecycle as CaseLifecycle
from app.cases.modules import ProjectModule
from app.git.models import GitRepository, Job, JobStatus, RepositoryStatus
from test_agents import OWNER, case_candidate_content, create_agent_run, create_workspace_project, make_client


def test_coverage_lookup_collects_records_from_coverage_sources(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    workspace, project = create_workspace_project(client)
    run_payload = create_agent_run(client, workspace["id"], project["id"])
    database = client.app.state.database
    database.init()

    with Session(bind=database.engine) as db:
        run = db.get(AgentRun, run_payload["id"])
        assert run is not None

        module = ProjectModule(
            workspace_id=workspace["id"],
            project_id=project["id"],
            name="Checkout",
            slug="checkout",
            code="CHECKOUT",
            path="/checkout",
            path_label="Checkout",
            depth=0,
        )
        db.add(module)
        db.flush()

        staged = AgentStagedOutput(
            agent_run_id=run.id,
            workspace_id=workspace["id"],
            project_id=project["id"],
            output_type=AgentStagedOutputType.case_candidate.value,
            status=AgentStagedOutputStatus.staged.value,
            title="Staged refund audit case",
            payload={
                "module_key": "CHECKOUT",
                "steps": ["Create an order", "Refund it"],
                "expected_result": "refund.created audit event is visible",
                "observability": {"audit_events": ["refund.created"]},
            },
            evidence_refs=[{"kind": "code_file", "ref_id": "repo:HEAD:src/checkout/refund.py"}],
            coverage_entries=[{"behavior_summary": "Staged refund audit coverage", "signals": [{"value": "refund.created"}]}],
        )
        db.add(staged)
        db.flush()

        db.add(
            CoverageIndexEntry(
                workspace_id=workspace["id"],
                project_id=project["id"],
                source_type="staged_output",
                source_id=staged.id,
                coverage_state=AgentStagedOutputStatus.staged.value,
                module_key="CHECKOUT",
                behavior_summary="Coverage index refund audit signal",
                signals=[{"value": "refund.created"}],
                evidence_refs=[{"kind": "code_file", "ref_id": "repo:HEAD:src/checkout/refund.py"}],
                confidence=90,
            )
        )

        test_case = CaseModel(
            workspace_id=workspace["id"],
            project_id=project["id"],
            lifecycle_status=CaseLifecycle.active.value,
            current_module_id=module.id,
            created_by=OWNER,
        )
        db.add(test_case)
        db.flush()
        revision = CaseRevision(
            workspace_id=workspace["id"],
            project_id=project["id"],
            test_case_id=test_case.id,
            revision_number=1,
            module_id=module.id,
            module_path_label="Checkout",
            content_snapshot={
                "title": "Formal refund audit trail",
                "module_id": module.id,
                "steps": ["Create a paid order", "Trigger a refund"],
                "expected_result": "Refund audit history contains refund.created.",
            },
            change_summary="seed formal coverage",
            created_by=OWNER,
        )
        db.add(revision)
        db.flush()
        test_case.current_revision_id = revision.id
        test_case.current_revision_number = 1

        repo = GitRepository(
            workspace_id=workspace["id"],
            project_id=project["id"],
            name="Checkout Repo",
            remote_url="file:///tmp/checkout.git",
            default_branch="main",
            mirror_path=str(tmp_path / "mirror.git"),
            status=RepositoryStatus.synced.value,
        )
        db.add(repo)
        db.flush()
        job = Job(
            workspace_id=workspace["id"],
            project_id=project["id"],
            repository_id=repo.id,
            job_type="diff_analysis",
            status=JobStatus.succeeded.value,
            created_by=OWNER,
            input_summary="base..target",
        )
        db.add(job)
        db.flush()
        analysis = DiffAnalysis(
            workspace_id=workspace["id"],
            project_id=project["id"],
            repository_id=repo.id,
            job_id=job.id,
            base_ref="base",
            target_ref="target",
            status=DiffAnalysisStatus.succeeded.value,
            created_by=OWNER,
        )
        db.add(analysis)
        db.flush()
        db.add(
            AISuggestion(
                workspace_id=workspace["id"],
                project_id=project["id"],
                diff_analysis_id=analysis.id,
                suggestion_type=AISuggestionType.case_candidate.value,
                status=AISuggestionStatus.suggested.value,
                title="AI refund audit candidate",
                rationale="Diff touches refund audit logging.",
                module_key="CHECKOUT",
                code_paths=["src/checkout/refund.py"],
                candidate_payload={
                    "steps": ["Create an order", "Refund it"],
                    "expected_result": "refund.created audit evidence is present",
                    "custom_fields": {"signals": [{"value": "refund.created"}]},
                },
                created_by=OWNER,
            )
        )
        db.commit()

        records = lookup_coverage_records(db, run=run, query="refund audit", module_key="CHECKOUT", max_results=20)

    source_types = {record["source_type"] for record in records}
    assert {"coverage_index", "staged_output", "formal_case", "ai_suggestion"} <= source_types
    assert all(record["module_key"] == "CHECKOUT" for record in records)


def test_classify_candidate_coverage_uses_coverage_index_interface() -> None:
    raw = json.loads(case_candidate_content())["case_candidates"][0]
    candidate = GeneratedCaseCandidate.model_validate(raw)

    duplicate = classify_candidate_coverage(
        candidate,
        [
            {
                "source_type": "formal_case",
                "source_id": "case_1",
                "coverage_state": "active",
                "module_key": "CHECKOUT",
                "title": "Validate refund audit trail",
                "behavior_summary": "Refund emits attributable audit and log signals.",
                "tokens": sorted({"validate", "refund", "audit", "trail"}),
                "signals": ["refund created"],
                "evidence_paths": ["src/checkout/refund.py"],
            }
        ],
    )

    assert duplicate["source"] == "deterministic_lookup"
    assert duplicate["classification"] == "high_confidence_duplicate"
    assert duplicate["recommendation"] == "reuse_existing_coverage"
    assert duplicate["matches"][0]["source_type"] == "formal_case"


def test_graph_analysis_compat_aliases_point_to_coverage_index_interface() -> None:
    from app.agents.graph_analysis import classify_duplicate, collect_coverage_records

    assert collect_coverage_records is lookup_coverage_records
    assert classify_duplicate is classify_candidate_coverage


def test_transition_staged_output_coverage_updates_entries(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    workspace, project = create_workspace_project(client)
    run_payload = create_agent_run(client, workspace["id"], project["id"])
    database = client.app.state.database
    database.init()

    with Session(bind=database.engine) as db:
        run = db.get(AgentRun, run_payload["id"])
        assert run is not None
        output = AgentStagedOutput(
            agent_run_id=run.id,
            workspace_id=workspace["id"],
            project_id=project["id"],
            output_type=AgentStagedOutputType.case_candidate.value,
            status=AgentStagedOutputStatus.staged.value,
            title="Staged refund audit case",
            payload={"module_key": "CHECKOUT"},
        )
        db.add(output)
        db.flush()
        entry = CoverageIndexEntry(
            workspace_id=workspace["id"],
            project_id=project["id"],
            source_type="staged_output",
            source_id=output.id,
            coverage_state=AgentStagedOutputStatus.staged.value,
            module_key="CHECKOUT",
            behavior_summary="Refund coverage",
            signals=[],
            evidence_refs=[],
        )
        db.add(entry)
        db.flush()

        next_state, entries = transition_staged_output_coverage(
            db,
            output=output,
            decision_status=AgentStagedOutputStatus.accepted,
            changed_at=entry.created_at,
        )

        assert next_state == "candidate"
        assert len(entries) == 1
        assert entries[0].coverage_state == "candidate"
        assert entries[0].verified_by_human is True
        assert output.coverage_entries[0]["coverage_state"] == "candidate"

        rejected_output = AgentStagedOutput(
            agent_run_id=run.id,
            workspace_id=workspace["id"],
            project_id=project["id"],
            output_type=AgentStagedOutputType.case_candidate.value,
            status=AgentStagedOutputStatus.staged.value,
            title="Rejected staged refund audit case",
            payload={"module_key": "CHECKOUT"},
        )
        db.add(rejected_output)
        db.flush()
        rejected_entry = CoverageIndexEntry(
            workspace_id=workspace["id"],
            project_id=project["id"],
            source_type="staged_output",
            source_id=rejected_output.id,
            coverage_state=AgentStagedOutputStatus.staged.value,
            module_key="CHECKOUT",
            behavior_summary="Rejected refund coverage",
            signals=[],
            evidence_refs=[],
            verified_by_human=True,
        )
        db.add(rejected_entry)
        db.flush()

        rejected_state, rejected_entries = transition_staged_output_coverage(
            db,
            output=rejected_output,
            decision_status=AgentStagedOutputStatus.rejected,
            changed_at=rejected_entry.created_at,
        )

        assert rejected_state == "rejected"
        assert len(rejected_entries) == 1
        assert rejected_entries[0].coverage_state == "rejected"
        assert rejected_entries[0].verified_by_human is False
        assert rejected_output.coverage_entries[0]["coverage_state"] == "rejected"
