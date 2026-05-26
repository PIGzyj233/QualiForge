# 架构决策记录

本目录维护 QualiForge 的架构决策记录（ADR）。一份 ADR 描述**一项**跨子系统、影响数据模型或安全边界的决定。

## 索引

| 编号 | 标题 | 状态 | 简述 |
|------|------|------|------|
| [0001](0001-agent-architecture.md) | AI Agent Architecture | Accepted | Temporal + LangGraph + ModelGateway 分层、子代理边界、Coverage Index、Staging 工作流 |
| [0002](0002-human-confirmed-module-mapping.md) | Human-Confirmed Module Trees and Code Mapping | Accepted | 模块树为人面向能力树、AI 仅建议、ModuleMappingRule 字段与生命周期 |

## 状态约定

- **Proposed**：草拟中，可在 PR 内继续讨论。
- **Accepted**：已落实方向，后续实现按此 ADR 推进。
- **Superseded by NNNN**：被后续 ADR 替代，需链回继任者。
- **Deprecated**：已不再适用，但保留历史。

## 写作约定

文件名：`NNNN-kebab-case-title.md`，编号 4 位左零填充，递增分配。

骨架：

```markdown
# ADR NNNN: 标题

## Status
Accepted | Proposed | Superseded by NNNN | Deprecated

## Context
背景与约束。说明为什么需要做这个决策。

## Decision
做出的决定（具体、可执行）。

## Consequences
落地后的影响（好的、坏的、需后续工作的）。

## Implementation Order
（可选）实施顺序与里程碑。
```

## 关系

- ADR 描述**决策**；落地的实现细节、字段表、状态机写到 `architecture/*.md`。
- 一个 ADR 在 Accepted 后，对应 `architecture/*.md` 应链回 ADR；当现状演化超出 ADR 范围时，更新 ADR 状态或新增继任者。
