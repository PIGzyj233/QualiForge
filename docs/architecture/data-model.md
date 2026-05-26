# 数据模型

本文档汇总 QualiForge 后端核心实体的字段与关系。完整字段以 `backend/app/**/models.py` 与各 slice 模型文件为准。

## 1. 实体全景

```
PlatformUser
  └─ WorkspaceMember ─► Workspace ─┬─► Project ─┬─► Repository (GitLab)
                                   │            ├─► ProjectModule (tree)
                                   │            │       └─► ModuleMappingRule
                                   │            ├─► TestCase ─► CaseRevision
                                   │            │       └─► Review
                                   │            ├─► CaseImportBatch
                                   │            ├─► DiffAnalysis
                                   │            ├─► AICaseCandidate
                                   │            ├─► TestPlan ─► PlanItem
                                   │            └─► Report
                                   ├─► AuditLog
                                   ├─► LLMProvider / ModelProfile / AIDataPolicy
                                   ├─► AIInvocationLog
                                   └─► AgentConversation ─► AgentRun
                                          ├─► AgentMessage
                                          ├─► AgentToolCall
                                          ├─► AgentApproval
                                          ├─► AgentStagedOutput
                                          └─► CoverageIndexEntry
                                          └─► AgentMemoryFile ─► AgentMemoryVersion
```

## 2. 平台 / Workspace

| 实体 | 关键字段 |
|------|---------|
| `PlatformUser` | `email (PK)`, `display_name`, `role`, `created_at` |
| `Workspace` | `id`, `name`, `slug`, `description`, `data_policy`, `created_at` |
| `WorkspaceMember` | `workspace_id`, `user_email`, `role: WorkspaceOwner/Member`, `joined_at` |
| `Project` | `id`, `workspace_id`, `name`, `code`, `description`, `primary_type`, `secondary_types[]`, `created_at` |
| `AuditLog` | `id`, `workspace_id`, `actor_email`, `action`, `entity_type`, `entity_id`, `before`, `after`, `created_at` |

## 3. AI 配置

| 实体 | 关键字段 |
|------|---------|
| `LLMProvider` | `id`, `workspace_id`, `name`, `provider_kind`, `api_base_url`, `api_key (encrypted)`, `default_headers`, `org_info` |
| `ModelProfile` | `id`, `provider_id`, `model_name`, `purpose`, `reasoning_effort`, `max_context`, `max_output`, `price_*`, `cache_strategy`, `timeout`, `retry`, `budget` |
| `AIDataPolicy` | `id`, `workspace_id`, `level: ExternalAllowed/NoSourceCode/InternalOnly/AIDisabled`, `notes` |
| `AIInvocationLog` | `id`, `workspace_id`, `project_id?`, `agent_run_id?`, `tool_call_id?`, `model_profile_id`, `purpose`, `input_summary`, `output_summary`, `tokens_in`, `tokens_out`, `cost`, `cache_hit`, `duration_ms`, `status`, `error_summary`, `created_at` |

## 4. Git Sandbox

| 实体 | 关键字段 |
|------|---------|
| `Repository` | `id`, `project_id`, `gitlab_url`, `default_branch`, `last_synced_sha`, `last_synced_at`, `size_mb` |
| `SandboxWorktree` | `id`, `repository_id`, `ref`, `path (system-generated)`, `expires_at` |

## 5. 模块与映射

详见 `architecture/module-mapping.md`。

| 实体 | 关键字段 |
|------|---------|
| `ProjectModule` | `id`, `project_id`, `parent_id?`, `name`, `code`, `description`, `keywords[]`, `owner`, `status` |
| `ModuleMappingRule` | `id`, `module_id`, `repository_id?`, `rule_type`, `pattern`, `relationship`, `status`, `source`, `ai_confidence`, `confidence`, `description`, `evidence_refs`, `accepted_from_output_id?`, `verified_by`, `verified_at?`, `stale_reason`, `conditions`, `case_sensitive?` |

枚举：

- `MappingRuleType`：`directory / file / api / service / command / library_api / symbol / package / build_target / config_key / database_migration / protocol / transport / format / codec / media_pipeline / asset_fixture / keyword`
- `MappingRelationship`：`primary / related / dependency / evidence`
- `MappingRuleStatus`：`active / stale / archived`
- `MappingSource`：`manual / ai_repository / ai_history / diff_confirmation`

## 6. 用例

| 实体 | 关键字段 |
|------|---------|
| `TestCase` | `id`, `project_id`, `module_id`, `title`, `content_form: structured/free_text`, `precondition`, `priority`, `risk`, `tags[]`, `links[]`, `applicable_versions`, `source`, `status: draft/pending_review/approved/rejected/archived`, `current_revision_id`, `custom_fields`, `created_at`, `updated_at` |
| `CaseRevision` | `id`, `case_id`, `version`, `content`, `steps[]`, `inferred_fields`, `ai_confidence`, `editor`, `reason`, `created_at` |
| `TestStep` | 嵌入 revision；配对 `action / expected` |
| `Review` | `id`, `case_id`, `revision_id`, `reviewer_email`, `decision: pass/reject/changes_requested/comment`, `comment`, `created_at` |
| `CaseImportBatch` | `id`, `project_id`, `file_name`, `file_storage_path`, `status`, `total_rows`, `accepted_count`, `rejected_count`, `created_by`, `created_at`, `finalized_at?` |
| `CaseImportItem` | `id`, `batch_id`, `raw`, `normalized`, `ai_confidence`, `status: pending/confirmed/rejected/promoted` |

## 7. Diff 分析

| 实体 | 关键字段 |
|------|---------|
| `DiffAnalysis` | `id`, `project_id`, `repository_id`, `base_ref`, `target_ref`, `status`, `summary`, `impacted_modules[]`, `risk_level`, `recommended_scope`, `recommended_regression[]`, `files`, `evidence`, `created_at`, `completed_at?` |
| `AICaseCandidate` | `id`, `diff_analysis_id?`, `project_id`, `title`, `content`, `proposed_module_id?`, `relationship_hints[]`, `evidence_refs[]`, `ai_confidence`, `status: pending/accepted/ignored/promoted`, `accepted_test_case_id?`, `created_at` |

## 8. 测试计划与执行

| 实体 | 关键字段 |
|------|---------|
| `TestPlan` | `id`, `project_id`, `name`, `kind: release/regression/smoke/feature/custom`, `version_label`, `owner_email`, `status`, `conclusion`, `report_id?`, `created_at` |
| `PlanItem` | `id`, `plan_id`, `source: case_snapshot/ai_suggestion/manual`, `case_id?`, `case_revision_snapshot?`, `ai_candidate_id?`, `assignee`, `execution_status: not_run/passed/failed/blocked/skipped`, `actual_result`, `failure_reason`, `defect_links[]`, `attachments[]`, `executed_by`, `executed_at?` |

## 9. 报告

| 实体 | 关键字段 |
|------|---------|
| `Report` | `id`, `plan_id`, `status: draft/confirmed/exported`, `summary`, `version_diff`, `scope`, `stats`, `failures_blocked`, `risk_assessment`, `ai_notes`, `release_decision`, `appendix`, `confirmed_by`, `confirmed_at?`, `created_at` |

## 10. Agent

详见 `architecture/ai-agent.md`。

| 实体 | 关键字段 |
|------|---------|
| `AgentConversation` | `id`, `workspace_id`, `project_id?`, `title`, `created_by`, `status: AgentConversationStatus`, `created_at`, `updated_at` |
| `AgentRun` | `id`, `conversation_id`, `workspace_id`, `project_id?`, `goal`, `mode: AgentRunMode`, `trigger_type`, `status: AgentRunStatus`, `current_phase`, `created_by`, `temporal_workflow_id`, `langgraph_thread_id`, `budget_snapshot`, `started_at?`, `completed_at?`, `cancelled_at?`, `failure_reason` |
| `AgentMessage` | `id`, `conversation_id`, `agent_run_id?`, `role: user/assistant/system/tool`, `content`, `content_summary`, `metadata`, `created_at` |
| `AgentToolCall` | `id`, `agent_run_id`, `parent_tool_call_id?`, `subagent_name?`, `tool_name`, `permission_level`, `input_summary`, `output_summary`, `status`, `idempotency_key`, `duration_ms`, `error_summary`, `created_at`, `completed_at?` |
| `AgentApproval` | `id`, `agent_run_id`, `approval_type`, `status`, `requested_by`, `decided_by?`, `request_summary`, `decision_summary`, `created_at`, `decided_at?` |
| `AgentStagedOutput` | `id`, `agent_run_id`, `workspace_id`, `project_id?`, `output_type`, `status: staged/accepted/rejected/superseded`, `title`, `payload`, `evidence_refs`, `quality_result`, `duplicate_result`, `coverage_entries`, `created_at`, `accepted_at?`, `rejected_at?` |
| `CoverageIndexEntry` | `id`, `workspace_id`, `project_id`, `source_type`, `source_id`, `coverage_state: staged/candidate/formal`, `module_id`, `module_key`, `behavior_summary`, `signals`, `evidence_refs`, `confidence`, `verified_by_human`, `created_at`, `updated_at` |
| `AgentMemoryFile` | `id`, `workspace_id?`, `project_id?`, `user_id?`, `scope: workspace/project/user/daily/curated`, `path`, `current_version`, `checksum`, `updated_by`, `updated_at` |
| `AgentMemoryVersion` | `id`, `memory_file_id`, `version`, `content`, `patch_summary`, `editor`, `reason`, `checksum`, `created_at` |

`AgentStagedOutput.output_type` 当前实际使用：

- `module_tree_draft`
- `module_mapping_suggestions`
- `module_refactor_suggestion`
- 用例 / 回归 / 报告等其他类型按业务扩展

## 11. ID / 时间 / JSON 约定

- 所有 ID 均为 `new_id()` 生成的 32 位 hex（`String(32)`）。
- 时间戳统一 UTC，`DateTime(timezone=True)`，`now_utc()` 写入。
- 自定义字段、`evidence_refs`、`signals` 等结构化数据使用 PostgreSQL JSONB；测试 SQLite 走 JSON 兼容字段。
- 枚举继承自 Python `StrEnum`，存储字符串。

## 12. Schema 演进

- **没有 Alembic**。schema 变更只通过模型加默认值 + `Base.metadata.create_all` 在首次取 session 时重建。
- 新增字段必须给 Python 端 default 或 server_default，确保旧库重建时不报错。
- 删除字段需要数据迁移脚本（暂无），目前以"标 archived + 停止写入"代替。
