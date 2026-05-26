# QualiForge 文档索引

QualiForge 是一个 AI 原生测试资产工作台，本目录是项目的产品、架构与运维文档单一入口。

## 目录结构

```
docs/
  product/         产品定位、PRD、路线图、产品不变式
  architecture/    系统拓扑与各子系统的实现说明
  operations/      部署、配置、本地开发
  adr/             架构决策记录（ADR）
  agents/          AI Agent skill 元数据（issue tracker / triage / domain layout）
  screenshots/     README 与文档引用的界面截图
```

## 阅读路径

按角色推荐：

- **新成员第一次上手**：`product/principles.md` → `architecture/overview.md` → `operations/development.md`
- **产品 / 设计**：`product/prd.md` → `product/roadmap.md` → `screenshots/`
- **后端开发**：`architecture/backend.md` → `architecture/data-model.md` → `operations/configuration.md`
- **前端开发**：`architecture/frontend.md` → `architecture/backend.md`（关注 API 入口）
- **AI Agent 方向**：`architecture/ai-agent.md` → `adr/0001-agent-architecture.md` → `architecture/data-model.md`
- **模块映射方向**：`architecture/module-mapping.md` → `adr/0002-human-confirmed-module-mapping.md`
- **部署 / 运维**：`operations/deployment.md` → `operations/configuration.md`

## 文档维护原则

1. **代码先行，文档跟进**：每个领域包的对外行为变化必须同步更新对应 `architecture/*.md`。
2. **决策入 ADR**：跨子系统、影响数据模型或安全边界的决定写 ADR；局部实现写到对应 architecture 文档。
3. **区分"已落地 / 设计中 / 推迟"**：架构文档使用 `Status` 段标注每个能力的实际状态，避免初稿与现状混淆。
4. **截图统一放 `docs/screenshots/`**，README 与文档统一使用相对路径引用。
5. **agent skill 元数据**（`docs/agents/`）独立维护，不混入产品/架构文档。

## 与根级文档的关系

| 根级文档 | 用途 |
|----------|------|
| `README.md` | 项目门户：定位、截图、快速启动、技术栈 |
| `CONTEXT.md` | 领域语言与产品概念（供 agent 与新成员快速建立词汇） |
| `CLAUDE.md` | Claude Code 在此仓库工作时的工程约定 |
| `AGENTS.md` | 通用 agent skill 配置入口，指向 `docs/agents/` |

详细产品、架构、运维内容一律下沉到本目录。
