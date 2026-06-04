# QualiForge 减法 PRD：GitLab 发版测试决策工作台

文档状态：CEO 多角色会审后定稿。
最后更新：2026-06-04。

## CEO Decision

QualiForge V1 不再优先证明自己是“AI 原生测试资产平台”。

V1 只证明一件事：

> 给有 GitLab 发版节奏的小团队，在一次 `base_ref -> target_ref` 发版前，快速生成“该测什么、为什么、测完能不能发”的证据链。

长期愿景仍然可以是 AI 测试资产平台，但第一版产品表面、导航、验收和实施都必须围绕“发版测试决策”收敛。

## Problem Statement

当前 QualiForge 已实现 Workspace、项目、Git 仓库、模块映射、用例导入、评审、Diff 分析、AI 建议、测试计划、执行记录、发布报告和 Agent Workbench 等能力。

问题不是能力不够，而是用户需要在多个管理页面之间理解内部实体：

- DiffAnalysis
- AISuggestion
- TestPlan
- PlanItem
- ReleaseReport
- ModuleMapping
- AgentStagedOutput

真实 QA 负责人每天要回答的不是这些系统对象，而是：

- 这次发版改了什么？
- 哪些模块受影响？
- 哪些必须测？
- 哪些没测，风险是什么？
- 失败和阻塞是否影响发布？
- 这份报告能不能直接发给负责人？

因此，下一轮产品优化必须把 QualiForge 从“平台功能集合”收敛成一次可完成的发版测试任务。

## Positioning

第一屏定位：

> QualiForge：GitLab 发版测试决策工作台
> 从版本 diff 生成测试范围、执行清单和发布报告。

AI 是增强能力，不是主角。

代码 diff、模块映射、AI 建议都只是证据。默认视角必须是 QA 发版决策视角。

## ICP

适合第一版的团队：

- 使用 GitLab 或 Git 仓库管理发版代码。
- 有 tag、branch、commit SHA 或类似版本边界。
- 每次发版需要 QA 负责人判断回归范围。
- 需要向研发负责人、项目经理或发布负责人解释发布风险。
- 已有一些历史用例或测试经验，但资产管理混乱。
- 觉得 TestRail、禅道等完整测试管理平台偏重。
- 目前用 Excel、飞书表格、GitLab checklist 或手工 Markdown 整理测试范围和报告。

## Anti-ICP

第一版不优先服务：

- 没有固定发版节奏的团队。
- 没有仓库接入权限的团队。
- 完全由开发自测、没有 QA 负责人判断范围的团队。
- 已经有成熟 TestRail、禅道或企业流程，并且不关心 diff 驱动测试范围。
- 需要自动化测试执行、CI/CD 编排或复杂缺陷系统集成的团队。

## Replacement Test

QualiForge V1 必须比替代方案赢在一个窄点上。

- Excel / 飞书表格：协作成本低，但不能自动理解代码变更。
- GitLab MR checklist：贴近研发流程，但 checklist 靠人工维护，历史覆盖不可追踪。
- TestRail / 禅道：测试管理完整，但对小团队偏重，也不天然解决 `tag diff -> 测试范围`。
- QualiForge：只赢在发版测试范围的证据链和报告生成速度。

如果 QualiForge 不能明显减少 QA 负责人看 diff、整理测试范围、写报告的时间，它就没有足够产品价值。

## V1 Must Have

### 1. 创建发版测试

用户创建一次发版测试时，填写：

- 发布名称
- Project
- Repository
- 目标版本
- 基准版本
- 测试环境
- 计划发布时间或发布窗口
- QA 负责人

Ref 选择应支持 tag、branch、commit SHA。不要只支持手输 tag。

### 2. 变更影响和风险清单

系统运行 diff，并以 QA 可理解的方式展示：

- 产品模块影响
- 高风险文件或变更类型
- 未映射文件
- 无正式用例覆盖的受影响模块
- 关键代码证据
- 推荐测试范围草案

代码文件列表是证据，不是主视图。

### 3. 测试范围草案

系统生成测试范围草案：

- 有正式 TestCase 时，推荐正式用例。
- 没有正式用例时，也必须生成临时检查项。
- 允许 QA 添加手工临时项。
- 允许 QA 排除推荐项。
- 排除高风险推荐项时必须填写原因。

AI 临时项是增强项，不是 V1 硬依赖。

### 4. 生成 Release TestPlan

从确认后的测试范围批量生成 release TestPlan 和 PlanItem。

正式用例必须保存 revision snapshot。

前端不能逐条拼接正式计划。后端必须提供批量创建接口，保证幂等、审计和失败一致性。

### 5. 执行记录

每个 PlanItem 至少支持：

- owner
- priority
- environment
- status: not_run / passed / failed / blocked / skipped
- actual_result
- failure_reason
- defect_link
- defect_status: open / fixed / verified / accepted_risk / not_applicable
- skip_reason
- evidence

没有负责人、环境、跳过原因和缺陷状态，报告不能作为正式发版依据。

### 6. 风险复核

报告前必须突出：

- failed items
- blocked items
- skipped items
- not_run items
- 未映射变更
- 无正式用例覆盖的受影响模块
- 高风险推荐项被排除的原因

### 7. 可直接发送的 Markdown 报告

报告必须默认可发送，不应要求 QA 二次整理。

报告必须回答：

- 这次发版测的是哪个版本、哪个环境、哪个时间窗口？
- 这次代码或功能主要改了什么？
- 哪些产品模块受影响？
- 哪些模块已经被测试覆盖？
- 哪些受影响模块没有正式用例覆盖？
- 哪些测试项失败、阻塞、跳过、未测？
- 失败项对应哪些缺陷，当前状态是什么？
- 是否存在未解决的发布风险？
- QA 的发布建议是什么？
- 谁确认了结论，确认时间是什么？
- 如果是带风险发布，风险接受人是谁？

### 8. 人工确认发布建议

最终发布建议必须由 QA 负责人确认。

可选结论：

- 建议发布
- 带风险发布
- 不建议发布
- 无法判断

系统和 AI 不能自动批准发布。

## V1 First-Use Paths

### Demo Path: 10-20 分钟出第一份样例报告

用户不需要 GitLab token，也不需要配置 AI。

流程：

1. 启动系统。
2. 登录后点击“体验一次发版测试”。
3. 使用内置 Demo Workspace、Demo Project、Demo Repository、Demo Tags、Demo Cases。
4. 选择默认 `v1.0.0 -> v1.1.0`。
5. 系统生成变更影响、测试范围和计划。
6. 用户标记几个通过、失败或阻塞项。
7. 导出 Markdown 报告。

Demo data 是 V1 必需品，不是 nice-to-have。

### Real Repository Path: 45-120 分钟出第一份可用报告

流程：

1. 创建 Workspace。
2. 配置 GitLab base URL 和 token。
3. 绑定一个仓库。
4. 系统同步 refs。
5. 用户选择 `base_ref -> target_ref`。
6. 如果没有 ModuleMapping，系统按顶层目录、常见目录名和文件类型生成临时模块视图。
7. 如果没有正式用例，系统生成临时检查项。
8. QA 执行测试项并导出报告。

AI、正式用例库、精细 ModuleMapping 都不能成为首次报告的硬阻塞。

## Degraded Mode

Release Run 必须支持降级运行：

- 无 AI：使用 deterministic diff、模块匹配、临时检查项。
- 无正式用例：生成临时测试项和手工项。
- 无精细 ModuleMapping：使用目录和文件类型生成临时模块视图。
- 仓库未同步：提示同步或触发同步，不让用户猜。
- ref 不存在：明确提示 base 或 target 不存在。
- GitLab token 失败：提示权限、地址、网络或 token 问题。

资产完整后更强，但资产不完整时也要能跑。

## Product IA

默认主路径：

- Release Runs
- Library
- Reviews
- Settings

高级入口进入 Advanced：

- Agent Workbench
- AI Config / Model Profile
- Workspace Audit
- 高级 ModuleMapping
- Agent staged outputs
- Agent memory
- Telemetry / Temporal / Prometheus 等运维细节

项目默认页应优先展示：

- 创建发版测试
- 最近 Release Runs
- 待执行项
- 待确认报告
- 仓库同步状态

不要让新用户先从 Diff、AI、Plans、Reports 这些内部对象开始。

## Architecture Decisions

### Release Run Identity

第一版不新增完整 `ReleaseRun` 表。

也不能做纯前端编排。

`TestPlan` 承担 Release Run 的持久执行身份，并新增最小 release context：

- `repository_id`
- `diff_analysis_id`
- `base_ref`
- `target_ref`
- `release_metadata`

`version_ref` 只能作为展示字段，不得作为 Release Run 唯一身份。

### Backend Flow

V1 后端流程：

```text
DiffAnalysis
  -> deterministic recommendation drafts
  -> TestPlan(release context)
  -> PlanItem
  -> ReleaseReport
```

必须提供：

- release runs projection API：返回项目下最近 release plans、diff、执行摘要和最新报告。
- diff workflow API：确保仓库已同步或给出明确错误，再运行 diff。
- deterministic recommendations API：非 AI 模式下也能给出测试范围草案。
- batch create release plan API：从选定推荐项一次性创建 TestPlan 和 PlanItems。
- release context response：前端可以恢复一次发版测试。

### Report Linkage

ReleaseReport 必须读取 TestPlan 的 release context。

如果关联了 DiffAnalysis，报告必须包含真实 diff 摘要、影响模块、未映射文件和风险证据。

如果没有关联 DiffAnalysis，报告必须标记为 manual release plan。

## Later

这些是增强项，不进入 V1 必需范围：

- AI 候选用例入正式库。
- 历史 Release Run 智能复用。
- GitLab Release / MR comment 回写。
- 模块映射 stale 评分。
- CoverageIndex 前端视图。
- 多人复杂评审流程。
- 缺陷系统深度集成。
- PDF 模板。
- 自动化测试执行。
- SaaS 多租户计费。

## Out Of Scope

V1 不做：

- 完整 TestRail / 禅道替代。
- 复杂企业权限矩阵。
- 自动运行项目代码、测试、构建或迁移。
- 任意仓库命令执行。
- 公网 SaaS。
- 公共 MCP Server。
- 新的通用 Agent Chat 主入口。
- 完整代码语义图谱。

## Success Metrics

V1 是否成功，看这些指标：

- 首次 Demo Release Run 10-20 分钟内完成。
- 真实仓库首次报告 45-120 分钟内完成。
- 不配置 AI 也能完成完整 Release Run。
- 没有正式用例库也能生成 diff 风险清单、临时测试项和报告。
- QA 负责人 5-10 分钟内得到变更影响和测试范围草案。
- Markdown 报告无需二次排版即可发送。
- QA 对推荐项的保留率可被记录，用作推荐命中率信号。
- 真实用户认为它减少了看 diff、整理测试范围、写报告的时间。

## Testing Decisions

测试只验证外部行为，不测实现细节。

必须覆盖：

- Demo data 跑通一份 Release Run 报告。
- 空用例库 + 无 AI + 临时模块 + 手工计划项 + Markdown 报告。
- 有正式用例时，生成计划保存 revision snapshot。
- 同 target ref、不同 base ref 不会复用错误计划。
- 同项目多仓库 release plan 不会互相污染。
- ReleaseReport 能读取真实 DiffAnalysis 摘要。
- GitLab token 无效、仓库未同步、ref 不存在时给出可理解错误。
- 高风险推荐项被排除时要求填写原因。
- failed / blocked / skipped / not_run 项进入风险复核和报告。
- QA 发布建议必须人工确认。

已有测试可复用：

- diff fixture 和 tag 分析测试。
- case review 状态机测试。
- test plan snapshot 和 execution 测试。
- release report Markdown 导出测试。

## Final Principle

Release Run 的默认视角必须是 QA 发版决策视角。

代码 diff、AI、模块映射都是证据，不是主流程语言。

第一版不要追求“资产完整后很强”，要追求“资产很乱时也能跑出第一份可信报告”。
