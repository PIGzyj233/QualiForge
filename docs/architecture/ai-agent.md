# AI Agent 架构

本文档描述 QualiForge Agent 子系统的**当前实现**，并区分已落地、部分落地与设计未实现部分。
设计依据是 [ADR 0001](../adr/0001-agent-architecture.md)。

## 1. 现状概览

| 能力 | 状态 | 实现位置 |
|------|------|----------|
| Temporal 持久执行 | ✅ 已落地 | `agents/temporal.py / workflows.py / activities.py` |
| LangGraph 主执行器 | ✅ 已落地 | `agents/graph_executor.py`（≈ 98KB） |
| 多种 specialized graph | ✅ 已落地 | `graph_analysis.py / graph_runner.py / graph_tools.py` |
| ModelGateway（OpenAI 兼容） | ✅ 已落地 | `ai/model_gateway.py` |
| 数据模型（Conversation/Run/Message/...) | ✅ 已落地 | `agents/models.py` |
| 工具注册表（typed code-read tools） | ✅ 已落地 | `agents/graph_tools.py` + `app/code_tools.py` |
| 预算（system/default/run 三层） | ✅ 已落地 | `agents/budget.py / graph_budget.py` |
| AI 数据策略检查 | ✅ 已落地 | 通过 `ai/config.py` 在 graph 入口校验 |
| Markdown 记忆 + 版本 | ✅ 已落地 | `agents/memory.py`，存储在 `agent_memory_root` |
| Coverage Index | 🟡 部分落地 | `agents/coverage.py`，前端尚未暴露完整视图 |
| Agent Workbench UI | ✅ 已落地 | `frontend/src/views/AgentWorkbenchView.tsx` |
| 多 Subagent 并行 | 🟡 部分落地 | `activities.py` 已支持 `temporal_child_results`；子代理选择仍偏静态 |
| Critic / Observability Gap 检测 | ⚠️ 设计但未完全落地 | 由 supervisor 内联实现，未独立 subagent |
| 外部 MCP / REST agent API | ⏸ 推迟 | Roadmap §3.1 |

> 区分原则：✅ 有对应路由/活动/测试；🟡 有代码但功能闭环不完整；⚠️ 写在 ADR 但只有部分骨架；⏸ 推迟到 roadmap。

## 2. 高层架构

```
Frontend AgentWorkbenchView (React)
  └─► FastAPI Agent API   (agents/routes.py, /api/.../agent/...)
        ├─► PostgreSQL：AgentConversation / Run / Message / ToolCall /
        │              Approval / StagedOutput / CoverageIndex
        └─► Temporal Workflow (workflows.py)
              └─► Activities (activities.py)
                    └─► LangGraph Supervisor (graph_executor.py)
                          ├─► Tool Registry (graph_tools.py)
                          ├─► (planned) Subagents
                          └─► ModelGateway (ai/model_gateway.py)
                                └─► OpenAI 兼容 endpoint（默认 DeepSeek）

  Markdown Memory ↔ agent_memory_root (volume)
```

## 3. 执行模式

| Mode | 用途 | 当前实现 |
|------|------|----------|
| Direct Answer | 小问题、轻量读取 | 直接同步执行 LangGraph，不一定创建 Temporal workflow |
| Preview | 只读分析 | 创建 `AgentRun(mode=preview)`，不落 staged output |
| Execute | 写入 staged output 与运行记录 | 创建 `AgentRun(mode=execute)`，由 Temporal 执行 |

升级到完整 `AgentRun + Temporal workflow` 的触发条件（在 `routes.py` 中判断）：

- 需要写 staged output / business draft。
- 跨多个工具或子代理。
- 需要进度可见、可取消、可恢复。
- 涉及大仓库扫描或大批量导入分析。
- 需要等待人工确认信号。

## 4. Temporal 与 LangGraph 的职责切分

**Temporal（外层持久执行）**：

- `AgentRunWorkflow` 启动 / 完成 / 取消 / 暂停 / 超时。
- 通过 signal 接收 cancel / pause / resume / approve。
- 重试瞬时错误；wall-clock 超时由 `agent_workflow_timeout_minutes` 控制。
- 启动子 workflow 处理大任务（如 `large_repo_scan`）。
- **不包含** agent 推理逻辑，调用 activity 即可。

**LangGraph（内层推理与工具）**：

- 维护当前 goal / conversation / 工具循环计划 / 子代理结果 / staged drafts。
- specialized graph 骨架：

```
load_context → plan → tool_loop → synthesize → verify
             → write_staged_outputs → summarize → memory_flush
```

- `tool_loop` 在预算内自治调用 typed 工具，结果回写到 graph state。
- `verify` 步骤里调用 critic 检查重复 / 证据 / 幻觉风险。

## 5. Supervisor 与 Subagent

**Supervisor**（`graph_executor.py` 内）：

- 决定是否启动子代理、启动几个、串/并行、是否需要 critic。
- 保持 subagent 只读 / 分析 / 提议；staged output 仅由 supervisor 写。
- 区分"可信指令"与"不可信分析内容"。

**初始 Subagent 类型（设计 / 部分落地）**：

| Subagent | 状态 | 用途 |
|----------|------|------|
| `CodeAnalysisSubAgent` | 🟡 部分 | 读码 / grep / diff / routes / config |
| `ImportAnalysisSubAgent` | 🟡 部分 | 读导入文件、字段映射、重复识别 |
| `CaseDesignSubAgent` | 🟡 部分 | 从已确认覆盖缺口创建候选用例 |
| `RegressionScopeSubAgent` | ⚠️ 设计 | 找应被复用/扩展的正式用例 |
| `CriticSubAgent` | ⚠️ 设计 | 重复风险、证据支撑、observability 缺口 |
| `ReportDraftSubAgent` | ✅ 已落地 | 从执行/风险/覆盖事实草拟报告 |

当前实现主要走 supervisor 内置策略 + Temporal child workflow（`temporal_child_results`），独立 LangGraph subagent 拆分是下一阶段任务。

## 6. 工具权限

`agents/graph_tools.py` 与 `app/code_tools.py` 暴露 typed 工具，权限分级：

| 级别 | 行为 | 例子 |
|------|------|------|
| `read` | 自动执行，记录审计 | `code_rg_files / code_search / code_read_range / git_diff / git_show_file / read_case_library / read_module_mapping` |
| `safe_mutation` | 自动执行，仅限运行记录与 staging | `create_staged_output / record_agent_note / update_agent_run_status / append_daily_memory` |
| `human_gate` | 需用户显式确认 | 大批量接受 staged output / 提交评审 / 修改正式资产 / 超预算继续 / 发送源码到外部 provider |

**Agent 永远拿不到自由 shell 工具。** 内部可能用到 `rg / sed / nl / git`，但被 wrap 成 typed 工具并 allowlist 路径。

### CodeReaderToolbox

- `code_rg_files`：按 glob 找文件。
- `code_search`：ripgrep 风格搜索。
- `code_read_range`：读文件行区间。
- `code_read_numbered_range`：带行号的读，用于精确证据引用。
- `git_status / git_diff / git_show_file`：沙盒只读 git。
- `parallel_code_read`：同预算与审计域下并行读。

## 7. Prompt 结构

Prompt 动态组装，分层版本化：

- **Global Policy Prompt**：代码可读、不可改、不可任意 shell、不可绕过评审、不可信内容标识、工具权限、子代理边界。
- **Domain Prompt**：Workspace / Project / Repository / Sandbox / Module / TestCase / CaseRevision / Review / DiffAnalysis / AICaseCandidate / TestPlan / PlanItem / Report / CoverageIndex / AgentRun。
- **Run Prompt**：用户目标、Workspace/Project、Repository/Ref、导入文件引用、模式、预算、期望输出。
- **Graph Prompt**：按任务（导入清洗 / diff 分析 / 用例生成 / 报告草稿）注入质量规则。
- **Tool Prompt**：可用工具、schema、权限、是否需要确认、期望证据输出。

每次运行记录 prompt 版本与 hash（写入 `AgentToolCall.metadata`）。

## 8. 数据模型

完整字段表见 `architecture/data-model.md`。这里仅列对照：

- `agent_conversations`：长期会话容器。
- `agent_runs`：单次执行单元，关联 `temporal_workflow_id` 与 `langgraph_thread_id`。
- `agent_messages`：用户/代理消息，含 `content_summary`。
- `agent_tool_calls`：每次工具调用，带 `permission_level / idempotency_key`。
- `agent_approvals`：人工 gate 的待审/已决。
- `agent_staged_outputs`：评审前的产物，含 `payload / evidence_refs / quality_result / coverage_entries`。
- `coverage_index_entries`：来自正式用例 / 候选用例 / staged output / 临时计划项 / diff / 代码证据 / 可观测信号。
- `agent_memory_files` + `agent_memory_versions`：Markdown 记忆与版本。

## 9. EvidenceRef

所有 staged output 与候选都必须带结构化证据引用：

```json
{
  "kind": "code_file",
  "ref_id": "repo_id:target_ref:path",
  "label": "backend/app/ai_config.py:404-430",
  "confidence": 0.86,
  "summary": "Provider creation masks API key and records audit.",
  "source": "code_search"
}
```

允许的 `kind`：`import_cell_range / import_row / code_file / grep_result / diff_hunk / diff_analysis / test_case / case_revision / module_mapping_rule / user_message / memory_entry / audit_event / metric / trace_point / log_signal`。

## 10. Coverage Index

`coverage_index_entries` 信号分类：

- `import_text_signals`：标题、步骤、预期、标签、模块字段、页面、角色、风险、优先级。
- `normalized_domain_signals`：业务行为、实体、用户旅程、场景类型、数据条件。
- `code_link_signals`：API route、function、class、config key、path、line range。
- `observability_signals`：日志关键词、审计事件、metric、trace point、job 状态。

每条信号附 `confidence` 与 `verified_by_human`。

Agent 在创建候选前**必须**做覆盖查找与重复检测（`coverage.py`）。

## 11. 预算

预算字段（`platform/config.py`）：

| 维度 | 默认 (`agent_default_*`) | 系统上限 (`agent_system_*`) |
|------|-------------------------|-----------------------------|
| `max_tool_calls` | 60 | 200 |
| `max_subagents` | 4 | 12 |
| `max_parallel_subagents` | 3 | 6 |
| `max_model_calls` | 20 | 40 |
| `max_case_candidates_per_run` | 30 | 100 |
| `max_wall_time_minutes` | 20 | 60 |
| `max_total_source_chars_sent` | 200 000 | 500 000 |

运行级覆盖：通过 `AgentRun.budget_snapshot` 在启动时确定，超限时 workflow 暂停并通过 `AgentApproval` 等待用户决策。

## 12. 可观测性

- 每个 workflow / activity / tool call 开 `agent_span`，写入 `AgentToolCall.duration_ms`。
- `AIInvocationLog` 与 `AgentToolCall` 双向 link：一次模型调用归属一个 tool call。
- Langfuse（可选）通过 `QUALIFORGE_TELEMETRY_LANGFUSE_*` 接入，可视化 LLM 链路。
- Temporal Web UI（`:8233`）查看 workflow 时间线、信号、重试。

## 13. 安全约束

- Agent 不能修改代码、不能任意 shell、不能跑测试或服务、不能访问业务数据库、不能批准评审、不能直接把 AI 输出提升为正式资产。
- Git clone / fetch / checkout / diff / show / grep / read 允许，因为不修改代码。
- 数据策略 (`ExternalAllowed / NoSourceCode / InternalOnly / AIDisabled`) 在 graph 入口和工具入口双重检查。
- Sandbox 路径检查、命令 allowlist、输出截断、所有调用审计。

## 14. 下一阶段

参见 `product/roadmap.md` §2.1 与 §3.1：

- 把 CriticSubAgent / RegressionScopeSubAgent 拆成独立 LangGraph 子图。
- 完成 CoverageIndex 的前端审阅视图。
- 暴露对外 REST agent API；评估 MCP Server。
- AIInvocationLog 聚合视图与按 Workspace 成本分摊。
