# 模块映射

模块树与映射规则是 QualiForge 把人类测试资产与代码证据连接起来的中枢。
设计依据见 [ADR 0002](../adr/0002-human-confirmed-module-mapping.md) 与 [ADR 0003](../adr/0003-centralize-module-mapping-rule-evaluation.md)。
本文档跟踪当前实现状态与后续阶段。

## 1. 现状概览

| 能力 | 状态 | 备注 |
|------|------|------|
| `ProjectModule.keywords` | ✅ 已落地 | JSON 列；项目级 `code` 唯一 |
| `ModuleMappingRule.repository_id` | ✅ 已落地 | 可选，code-path 规则建议绑定仓库 |
| 扩展 `MappingRuleType` 枚举 | ✅ 已落地 | 见 §3 |
| `MappingRelationship` (primary/related/dependency/evidence) | ✅ 已落地 | |
| `MappingRuleStatus` (active/stale/archived) | ✅ 已落地 | |
| `MappingSource` (manual/ai_repository/ai_history/diff_confirmation) | ✅ 已落地 | |
| `ai_confidence / confidence / evidence_refs / accepted_from_output_id / verified_by / verified_at / stale_reason / conditions / case_sensitive` | ✅ 已落地 | |
| Module Mapping Admin UI | ✅ 已落地 | `frontend/src/views/ModuleMappingAdmin.tsx` |
| AI 生成模块树草稿 → staged output | ✅ 已落地 | commit `23caa0f`，走 `AgentStagedOutput.output_type = module_tree_draft` |
| 映射规则的 AI 建议批量产出 | 🟡 部分 | supervisor 可生成，但 preflight 与冲突 UI 仍待补 |
| Repository 静态索引（`repository_id + commit_sha`） | ⏸ 未实现 | Roadmap §2.2 |
| Diff 分析按 `relationship + status` 加权 | 🟡 部分 | 引擎已识别 status，但权重计算尚在演进 |
| 映射规则 import/export (YAML/JSON) | ⏸ 未实现 | Roadmap §2.2 |

## 2. 模块树

模块树是**人面向**的功能/能力树，不是代码架构树。

- 建议保持 2 ~ 3 层：领域 → 可独立测试的能力区域 → （可选）子能力。
- 单条测试场景**不要**变成模块节点。
- 单父树（非 DAG）。跨切关系用 tag / related module / 未来 module link 表达。

字段：

- `name`：人可读名称，可编辑。
- `code`：项目级稳定业务编码，重命名/移动不自动改。
- `description`：一句话职责说明。
- `keywords`：人填或 AI 建议的关键词。
- `owner`：当前 owner；未来支持结构化 owner / reviewer。

## 3. 映射规则

`ModuleMappingRule` 字段（与 `backend/app/cases/modules.py` 一致）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `repository_id` | 可空 | code-path 规则建议绑定 |
| `rule_type` | `MappingRuleType` | 见下表 |
| `pattern` | 字符串 | glob / 标识 / API route / 命令 / 符号 / 关键词 |
| `relationship` | `primary / related / dependency / evidence` | 决定 diff 权重 |
| `status` | `active / stale / archived` | 生命周期 |
| `source` | `manual / ai_repository / ai_history / diff_confirmation` | 创建来源 |
| `ai_confidence` | 0-100 | AI 初始置信度 |
| `confidence` | 0-100 | 当前综合置信度 |
| `description` / `reason` | 字符串 | 人读说明 |
| `evidence_refs` | JSON | 结构化引用，**不存大段源码** |
| `accepted_from_output_id` | 可空 | 若来自 staged output |
| `verified_by / verified_at` | | 当前人工确认元数据 |
| `stale_reason` | 字符串 | 为何需要复查 |
| `conditions` | JSON | 平台 / 语言 / 构建目标 / 项目类型等约束 |
| `case_sensitive` | 可空 | 覆盖默认匹配规则 |

`MappingRuleType` 当前枚举（首批扩展集）：

```
directory  file  api  service  command  library_api  symbol  package
build_target  config_key  database_migration
protocol  transport  format  codec  media_pipeline
asset_fixture  keyword
```

`media_pipeline` 故意保持高层粒度，覆盖编解码 / 滤镜 / 转码 / 同步 / 缓冲等媒体处理链，避免每个子系统都拆成独立规则类型。

## 4. 匹配语义

> ADR 0003 已决定：匹配语义应集中到一个 ModuleMapping rule evaluation Module。当前代码仍有部分调用方本地实现，后续应迁移到统一 `evaluate_mapping(...)` / `preflight_rule(...)` Interface。

- 路径类规则使用 glob；支持 `!pattern` 排除（排除胜出）。
- 匹配是**加权**的，不是布尔：diff 分析 / 确认时综合考虑 `relationship` 权重、`confidence`、verification 状态、specificity、`status`。
- specificity 简单可解释：
  - 精确文件 > glob
  - 通配少的 > 通配多的
  - 固定前缀长的 > 短的
  - 文件 / 目录规则通常强于 keyword 规则
  - 排除 > 包含
- 代码路径默认大小写敏感；关键词 / command / api / config 默认大小写不敏感（可被规则或项目覆盖）。

示例：

```
libavcodec/h264*
!libavcodec/h264_metadata*

backend/app/cases/**
!backend/app/cases/review_*
```

## 5. Primary 归属与冲突

目标：在项目 / 仓库范围内，每条代码路径最多一个 `primary` 模块；可以有多个 `related / dependency / evidence`。

系统不在写入时硬拒绝重叠 primary——repository 扫描与 diff 分析会**汇报冲突**，请用户通过收窄 pattern 或改 relationship 解决。

## 6. 生命周期

| 状态 | 行为 |
|------|------|
| `active` | 正常参与 diff 分析与推荐 |
| `stale` | 弱参与并明显标记需复查 |
| `archived` | 保留历史，默认不参与 |

变 stale 的常见原因：

- 模块职责或关键词大幅变化。
- pattern 不再匹配任何文件。
- 大量被匹配文件移动或消失。
- 仓库扫描发现更强的相反归属。
- 用户反复纠正 diff 影响结果。

轻量重命名不应自动让所有规则 stale。

## 7. 证据引用

`evidence_refs` 存可追溯指针与摘要，不存全文。示例：

```json
[
  {
    "type": "file",
    "repository_id": "repo_123",
    "ref": "main",
    "commit_sha": "abc123",
    "path": "libavcodec/h264dec.c",
    "symbol": "ff_h264_decoder",
    "line_start": 123,
    "line_end": 180,
    "reason": "decoder registration"
  }
]
```

源码片段在需要时由 Sandbox 现取。数据库只保留结构化引用、摘要、hash、行号。

## 8. 项目类型

`Project` 支持一个主要类型与可选次要类型。当前词表：

- Web application
- Mobile app
- Desktop app
- CLI tool
- SDK / library
- Data or algorithm engine
- Streaming / media codec endpoint
- Embedded / firmware
- Other

项目类型驱动 AI 模板与扫描策略，**不**硬限制用户能创建的规则种类。

## 9. AI 模块树草稿与映射建议

流程：

1. 用户在 ModuleMappingAdmin 触发 "AI 建议模块树"（或映射建议）。
2. `cases/modules.py` 写 `AgentRun(mode=execute)`，`start_agent_run_workflow` → Temporal。
3. supervisor 调用 CodeAnalysisSubAgent / 重读历史用例。
4. 产物落 `AgentStagedOutput`：
   - `output_type = module_tree_draft`：完整模块树草稿。
   - `output_type = module_mapping_suggestions`：批量映射建议项。
5. 用户在 UI 内接受 / 编辑 / 拒绝；接受 handler 在 `cases/modules.py` 内转化为正式 `ProjectModule` / `ModuleMappingRule`，并记录 `accepted_from_output_id`。

建议项形态：

- target module / repository / rule_type / pattern / relationship
- ai_confidence / 提议的 current confidence
- reason
- 正向 evidence_refs
- 警示 / 反向 evidence
- 建议 status

### Preflight 检查（计划中）

接受前应验证：

- pattern 命中目标（路径类）。
- 重复或近重复规则。
- primary 冲突。
- 过宽匹配（命中过多目录）。
- vendor / third-party / generated / build output 匹配。
- 仓库 ref 失效或缺仓库。

默认：

- vendor / third-party / dependency / build / generated output 默认从建议中排除。
- 测试文件默认是 evidence，不是强 primary。
- 排除胜过包含。

## 10. Diff 分析集成

规则在 diff 分析中的角色：

- `active` 正常参与；`stale` 弱参与并显式标记；`archived` 默认不参与。
- `primary` 驱动核心影响；`related` 驱动次级影响；`dependency` 驱动风险提示；`evidence` 不作为直接实现影响。

Diff 输出应分离：

- 核心影响（primary）
- 关联影响（related）
- 依赖 / 观察风险（dependency）
- 映射冲突
- stale 映射告警

回归建议应分离：

- 核心回归
- 扩展回归
- 观察项

## 11. 测试资产与媒体资产

- 测试文件可作 evidence 参与归属推断，但默认不是强映射；只有人工确认时才转为模块测试资产或正式 evidence。
- 媒体 / 二进制资产按 path / type / size / 命名 / manifest 引用做轻量索引，**MVP 不解析内容**。

## 12. 仓库分析边界

允许：`git clone/fetch/checkout/read`、`git diff/show/ls-files`、`rg`、静态/AST/tree-sitter 解析、manifest 与文档解析。

默认禁止：运行测试 / 构建脚本 / 启动服务 / 跑迁移 / 连业务数据库 / 执行仓库脚本。

仓库扫描需以 `repository_id + commit_sha` 为 key 建可复用索引；MVP 索引含文件清单与轻量符号/入口；完整依赖或调用图推迟。

## 13. 模块合并与拆分

需显式迁移预览：

- **合并**：源模块资产迁到目标，源模块归档，写审计。
- **拆分**：先提议用例 / 映射 / 关键词的分配，由人确认。
- 源模块**不硬删**：当历史含义需保留时，保留 `archived` 状态。
