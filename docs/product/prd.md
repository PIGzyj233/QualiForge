# QualiForge MVP PRD

文档状态：MVP 12 条主线已交付，进入打磨与下一阶段规划。
最后更新：2026-05-26。

## 1. 产品定位

QualiForge 是面向小到中型研发/测试团队的 AI 原生测试资产平台。

它不是传统测试管理工具的替代品，而是让团队和 AI Agent 都能系统性理解测试资产与代码变更的工作台。平台将 GitLab 仓库、版本 diff、历史测试用例、用例评审、测试计划执行结果与发布报告统一成结构化上下文。

第一版优先服务管理混乱的小团队：已有 Excel / CSV / 飞书表格 / 文档中的零散用例，但缺少统一治理，也无法让 AI Agent 稳定获得已有用例与代码仓库上下文。

## 2. 核心问题

- 历史测试用例散落在不同文档和表格中，结构不统一。
- 测试用例缺少评审流程，正式用例库质量不可控。
- 发布版本时，测试负责人难以根据 Git tag diff 系统性判断应该测什么。
- AI 生成测试用例时缺少上下文，无法充分利用已有用例、模块知识和代码仓库信息。
- 测试计划执行结果与测试报告依赖人工整理，结论难追溯。
- 小团队不适合复杂权限矩阵，但仍需要基本治理与可追溯性。

## 3. MVP 价值闭环

> 旧用例进入平台 → Git 仓库进入沙盒 → AI 获得结构化上下文 → 基于 diff 与已有用例生成建议 → 人工评审进入正式库 → 加入测试计划执行 → 输出报告 → 执行结果反哺资产。

MVP 五条主闭环：

1. Workspace、项目、GitLab 仓库接入。
2. Excel / CSV 历史用例 AI 整理导入。
3. 用例库、评审流、状态管理、历史快照。
4. Git tag diff 分析，结合已有用例生成测试建议与候选用例。
5. 测试计划执行录入，生成 Web 在线报告与 Markdown 报告。

## 4. MVP 交付状态

12 条主线全部完成（与 `backend/app/main.py::dashboard_summary` 中的 `work_items` 对齐）：

| # | 主题 | 负责领域包 | 状态 |
|---|------|------------|------|
| #1 | 初始化私有化工作台 | `platform/` | done |
| #2 | Workspace、成员、项目、基础审计 | `workspace/` | done |
| #3 | LLM Provider / Model Profile / AI 数据策略 | `ai/` | done |
| #4 | GitLab 只读仓库与 Git Sandbox | `git/` | done |
| #5 | 模块 / 功能域与 ModuleMapping 规则 | `cases/modules.py` | done |
| #6 | Excel/CSV 历史用例导入为草稿 | `cases/imports.py` | done |
| #7 | 评审候选用例并沉淀正式用例库 | `cases/reviews.py` | done |
| #8 | tag diff 分析并展示模块影响 | `cases/diff_analysis.py` | done |
| #9 | 基于 Diff 生成 AI 测试建议与候选用例 | `cases/ai_suggestions.py` | done |
| #10 | 从正式用例与 AI 建议创建测试计划 | `planning/test_plans.py` | done |
| #11 | 执行计划项并录入结果与证据 | `planning/test_plans.py` | done |
| #12 | 生成、确认、导出发布测试报告 | `planning/release_reports.py` | done |

附加已落地能力（不在原 12 条列表，但已实现）：

- AI Agent Workbench：Temporal + LangGraph 执行器、AgentConversation/Run/Message/StagedOutput 数据模型、前端 `AgentWorkbenchView` （详见 `architecture/ai-agent.md`）。
- ModuleMapping 字段扩展：`keywords / relationship / status / ai_confidence / evidence_refs / repository_id` 等已落地，AI 生成模块树草稿可走 staged output 审核（详见 `architecture/module-mapping.md`）。
- Telemetry：OpenTelemetry trace + Prometheus metrics + Langfuse 可选接入（`platform/telemetry.py`）。

## 5. 非目标

MVP 阶段明确不做：

- 自动化测试执行 / CI/CD 深度集成。
- Agent 启动项目、运行服务、访问业务数据库。
- 复杂权限矩阵与多人复杂审批流。
- 客户级审计报告 / 电子签名 / 合规模板。
- 全量代码语义图谱。
- Elasticsearch / 独立向量数据库。
- Jira / 禅道 / 飞书 / Slack 等深度集成。
- 对外 MCP Server。
- 公网 SaaS 优先交付。

后续演进见 `product/roadmap.md`。

## 6. 用户与权限

### PlatformAdmin

- 管理平台用户和全局配置。
- 配置全局 GitLab 地址白名单或默认 GitLab URL。
- 配置全局 AI 数据策略默认值与系统级 LLM Provider。
- 查看平台级审计、任务和成本汇总。

### WorkspaceOwner

- 创建和管理 Workspace、成员、项目。
- 配置 Workspace 级 GitLab token、模型与 AI 数据策略。
- 配置模块、映射规则、导入策略。
- 确认或调整报告结论。

### WorkspaceMember

- 创建、编辑草稿用例，提交评审。
- 评审其他成员提交的用例（默认不允许自评审，Owner 可放开）。
- 创建和执行测试计划。
- 查看测试报告。

默认规则：候选用例至少需 1 名成员通过才能进入正式用例库。

## 7. 信息架构

登录后默认进入工作台 Dashboard，而不是项目列表。

Workspace 顶层导航：

- 工作台总览（`/w/:wid`）。
- 项目列表与项目工作台（`/w/:wid/p/:pid/...`）。
- Workspace 管理（成员 / 项目 / 审计）。
- Workspace 设置（AI 配置等）。

项目内导航：

- 概览（overview）/ 团队（team）。
- 模块映射（modules）/ 仓库（repo）。
- 用例库（library）/ 用例导入（imports）/ 评审（reviews）。
- Diff 分析（diffs）/ AI 建议（ai）/ Agent Workbench（agent）。
- 测试计划（plans）/ 发布报告（reports）。

具体路由映射见 `architecture/frontend.md`。

UI 风格：安静、密集、工作台式 SaaS 管理工具；少营销化大卡片；AI 作为任务流中的辅助分析能力，而非唯一入口。

## 8. 核心功能需求

> 下文是 MVP 阶段对外承诺的能力清单。实现细节、字段、状态机均参见 `architecture/data-model.md` 与各 `architecture/*.md`。

### 8.1 Workspace 与项目

- 支持创建 Workspace 与多项目。
- Workspace 成员管理；私有化部署仍保留多租户模型。

### 8.2 GitLab 仓库接入

- WorkspaceOwner 配置 GitLab token（只读权限：repo / tags / commits / diff）。
- token 加密存储，不向普通成员展示。
- 项目可绑定一个或多个 GitLab 仓库；平台维护只读 clone/mirror。

### 8.3 Git 沙盒

- 平台维护 bare mirror，分析 tag diff 时创建临时 worktree。
- worktree 路径由系统生成；不接受用户传入任意本地路径。
- Workspace / Project 目录级隔离；禁止符号链接逃逸。
- 支持仓库大小、diff 文件数、任务超时限制。

### 8.4 模块 / 功能域 与 模块映射

- 项目下维护模块树（建议 2~3 层，叶子是可独立测试的能力区域）。
- 模块字段：`name / code / description / keywords / owner`。
- 映射规则关联代码路径、文件、API、服务、命令、库 API、符号、包、构建目标、配置 key、数据库迁移、协议、传输、容器格式、编解码器、媒体管线、测试资产、关键词等技术对象。
- 映射来源：人工 / AI 仓库推断 / AI 历史用例推断 / Diff 确认。
- 映射规则有 `relationship: primary | related | dependency | evidence` 与 `status: active | stale | archived`。
- AI 模块树草稿与映射建议进入 `AgentStagedOutput`，需要人接受。

### 8.5 历史用例 AI 导入

支持上传 Excel/CSV：

1. 上传文件。
2. AI 识别表头、字段、合并单元格、多行步骤等结构。
3. AI 转换为平台标准用例草稿。
4. 用户在预览页批量修正和确认。
5. 用户选择提交评审，或由 WorkspaceOwner 批量导入为正式用例。
6. 系统记录原始文件、导入批次、AI 转换结果与人工确认。

### 8.6 用例库与评审

用例状态：`draft / pending_review / approved / rejected / archived`。

模型：

- `TestCase`：承载当前用例内容和状态。
- `CaseRevision`：记录历史快照。
- `Review`：记录评审过程。
- `PlanItem`：加入测试计划时保存用例快照，避免后续用例修改影响历史计划。

评审操作：通过 / 驳回 / 要求修改 / 评论 / 编辑候选内容。

修改正式用例应产生新 revision，可按配置重新进入评审。

### 8.7 用例字段

固定核心字段：标题、模块/功能域、前置条件、步骤、预期结果、优先级、风险等级、标签、需求/缺陷链接、适用版本范围、来源、状态。

系统推断字段：关联代码路径、接口、服务、配置/迁移、关联 diff 分析、AI 置信度、关联依据。

支持自定义字段（名称、是否必填、显示顺序、字段类型）。

核心字段语义不允许被团队删除或重定义。

### 8.8 用例内容形态

支持 `structured`（步骤式，多步操作配对预期）与 `free_text`（自由文本，导入初期或探索性测试）。正式用例优先标准化为步骤式。

### 8.9 Diff 分析

输入：Project / Repository / baseRef / targetRef。

分析三层：

1. 文件级：变更文件、目录、语言、服务/模块归属、变更类型。
2. 文本/结构级：新增/删除/修改的函数、类、接口路由、配置 key、SQL/迁移文件、测试文件。
3. AI 解释级：影响面、风险点、候选用例、推荐回归范围。

输出：变更摘要、影响模块、风险等级、推荐测试范围、推荐回归用例、AI 候选新增用例、变更文件列表、依据与置信度。

页面以测试决策优先，而不是以文件列表优先。

### 8.10 AI 测试建议与候选用例

AI 输出分两类：

- 本次版本测试建议（服务当前测试计划，不一定长期保存）。
- 可沉淀候选用例（经过评审后进入正式库）。

候选用例可直接作为本次计划临时测试项加入测试计划执行，但不能直接进入正式库。

所有 AI 输出必须展示：来源 diff、命中的模块映射规则、关联已有用例、关联代码路径/接口/配置、生成理由、置信度、人工反馈入口（确认 / 忽略 / 修改）。

### 8.11 测试计划

类型：`release / regression / smoke / feature / custom`，MVP 重点优化 `release`。

模型：`TestPlan`（范围、版本、负责人、状态、结论、报告内容）与 `PlanItem`。

`PlanItem` 来源：正式用例快照 / AI 临时建议 / 手工临时项。

执行状态：`not_run / passed / failed / blocked / skipped`。MVP 支持整条用例结果与备注，不强制步骤级结果。

### 8.12 测试执行界面

支持两种视图：

- 表格/列表视图（负责人查看整体进度、分配执行人、筛选失败/阻塞）。
- 单项执行视图（测试人员逐条查看、填写结果、上传证据、链接缺陷）。

执行时支持分配执行人、标记状态、填写实际结果、填写失败原因、添加缺陷链接、上传附件或截图、记录执行人与时间。

### 8.13 测试报告

报告要回答：版本测了什么 / 什么没测 / 失败和阻塞在哪里 / 风险是否可接受 / 是否建议发布。

结构：Summary / Version & Diff / Scope / Execution Statistics / Failed-Blocked Items / Risk Assessment / AI Notes / Release Decision / Appendix。

AI 可生成草稿与风险摘要，最终结论必须由负责人确认。

导出优先级：Web 在线报告 → Markdown 导出 → PDF（后置或通过浏览器打印兜底）。

### 8.14 LLM Provider 与模型配置

MVP 支持 OpenAI 兼容 API。默认对接 DeepSeek。

配置分两层：

- Provider：API Base URL、API Key、默认 header、组织信息。
- Model Profile：model name、用途、思考等级、最大上下文、最大输出、价格、缓存策略、超时、重试、预算限制。

Model Profile 支持按用途区分：导入清洗 / diff 分析 / 用例生成 / 报告总结 / Agent 调用。

记录 token 使用量、调用成本、缓存命中、耗时、失败原因。详细环境变量见 `operations/configuration.md`。

### 8.15 AI 数据策略

WorkspaceOwner 配置 AI 数据策略，默认策略由 PlatformAdmin 设置。

策略分级：`ExternalAllowed / NoSourceCode / InternalOnly / AIDisabled`。

AI 任务开始前必须检查数据策略。日志只记录输入摘要与数据类型，不记录完整敏感 prompt。

### 8.16 Job、Agent Run 与后台任务

耗时工作走后台：Git clone/sync、tag diff 分析、代码结构索引、Excel/CSV 导入解析、AI 用例整理、AI 候选用例生成、报告草稿、Markdown 导出。

MVP 引入 Temporal 承担 `AgentRun` 持久执行；其他长任务目前以 FastAPI BackgroundTasks 兜底，Worker 进程承担 Redis 心跳与未来 job 调度。

`AgentRun` 与 `Job` 的状态机、记录字段、重试策略见 `architecture/ai-agent.md` 与 `architecture/data-model.md`。

### 8.17 缓存

缓存分三类：Git/代码索引缓存 / AI 任务结果缓存 / LLM prompt-semantic cache。

缓存不允许覆盖：人工评审结论、测试执行结果、负责人最终报告结论、权限判断、数据策略判断。缓存命中需对用户可见。

### 8.18 审计

必须记录的事件类别：登录登出、Workspace 成员增删改、GitLab token 配置（不记 token 明文）、仓库接入/同步/删除、AI 数据策略变更、LLM Provider/Model Profile 变更、用例创建/修改/状态变更、评审通过/驳回/要求修改、批量导入确认、测试计划创建/范围变更/执行结果变更、缺陷链接添加/修改、报告草稿生成/人工确认/结论修改、AI 任务执行摘要与成本、缓存命中关键记录。

MVP 不要求复杂审计查询，但对象详情页应能看到相关历史。

## 9. 技术架构基线

模块化单体，技术栈：FastAPI / React + TS / PostgreSQL / Redis / Temporal / Docker Compose 私有化。

详见 `architecture/overview.md`。

## 10. MVP 验收标准（已达成）

- 一个 Workspace 可接入 GitLab 仓库并完成只读同步。
- 一个项目可上传 Excel/CSV，由 AI 转换为平台用例草稿。
- 用户可预览、修正、提交评审，并将用例纳入正式库。
- 用户可配置模块与映射规则。
- 用户可选择两个 tag 生成 diff 分析。
- diff 分析可展示影响模块、推荐回归用例、AI 候选用例与依据。
- AI 候选用例可作为临时测试项加入测试计划，也可提交评审。
- 测试人员可执行计划项并录入结果、缺陷链接和附件。
- 负责人可确认最终报告结论。
- 系统可生成 Web 报告与 Markdown 报告。
- 关键操作有审计记录。
- AI 调用有成本、缓存、任务状态记录。
