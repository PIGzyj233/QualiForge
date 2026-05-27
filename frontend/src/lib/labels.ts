import type { AIDataPolicy, AIPurpose } from "../api/ai";
import type { MappingRelationship, MappingRuleType, MappingSource, MappingStatus } from "../api/cases";
import type { PlanItemRecord } from "../api/planning";

export const statusLabel: Record<string, string> = {
  done: "已完成",
  in_progress: "进行中",
  next: "下一步",
  blocked: "等待依赖",
  ok: "正常",
  degraded: "降级",
  unavailable: "不可用",
  configured: "已配置",
  queued: "排队中",
  rejected: "已拒绝",
  succeeded: "成功",
  failed: "失败",
  active: "活跃",
  archived: "归档",
  pending: "待同步",
  synced: "已同步",
  sync_failed: "同步失败",
  running: "运行中",
  waiting_for_user: "等待用户",
  cancelled: "已取消",
  uploaded: "已上传",
  preview_ready: "可预览",
  review_submitted: "已提交评审",
  imported: "已入库",
  draft: "草稿",
  editing: "编辑中",
  in_review: "评审中",
  confirmed: "已确认",
  pending_review: "待评审",
  pending_owner_confirmation: "待负责人确认",
  approved: "已通过",
  submitted: "已提交",
  changes_requested: "要求修改",
  commented: "已评论",
  edited: "已编辑",
  suggested: "已建议",
  accepted: "已采纳",
  ignored: "已忽略",
  modified: "已修改",
  not_run: "未执行",
  todo: "待执行",
  passed: "通过",
  skipped: "跳过",
  formal_case: "正式用例",
  ai_temp: "AI 临时项",
  manual: "手工项",
  import: "导入",
  ai_suggestion: "AI 建议",
  active_edit: "正式编辑稿",
  no_review: "无评审",
  release: "发布计划",
  regression: "回归计划",
  smoke: "冒烟计划",
  feature: "功能计划",
  custom: "自定义计划",
  hold_release: "暂缓发布",
  approve_release: "建议发布",
  conditional_release: "有条件发布",
  checking: "检查中"
};

export const riskLabel: Record<string, string> = {
  low: "低风险",
  medium: "中风险",
  high: "高风险"
};

export const changeTypeLabel: Record<string, string> = {
  added: "新增",
  modified: "修改",
  deleted: "删除",
  renamed: "重命名"
};

export const suggestionTypeLabel: Record<string, string> = {
  regression: "回归建议",
  case_candidate: "候选用例"
};

export type ExecutionStatus = Exclude<PlanItemRecord["status"], "todo" | "in_progress">;

export const executionStatuses: ExecutionStatus[] = ["not_run", "passed", "failed", "blocked", "skipped"];

export const purposeLabel: Record<AIPurpose, string> = {
  import_cleanup: "导入清洗",
  diff_analysis: "Diff 分析",
  case_generation: "用例生成",
  report_summary: "报告总结"
};

export const policyLabel: Record<AIDataPolicy, string> = {
  ExternalAllowed: "ExternalAllowed",
  NoSourceCode: "NoSourceCode",
  InternalOnly: "InternalOnly",
  AIDisabled: "AIDisabled"
};

export const mappingRuleTypeLabel: Record<MappingRuleType, string> = {
  directory: "目录",
  file: "文件",
  api: "接口",
  service: "服务",
  command: "命令",
  library_api: "库 API",
  symbol: "符号",
  package: "包",
  build_target: "构建目标",
  config_key: "配置 Key",
  database_migration: "数据库迁移",
  protocol: "协议",
  transport: "传输",
  format: "格式",
  codec: "编解码",
  media_pipeline: "媒体链路",
  asset_fixture: "资产/Fixture",
  keyword: "关键词"
};

export const mappingRelationshipLabel: Record<MappingRelationship, string> = {
  primary: "主归属",
  related: "相关",
  dependency: "依赖",
  evidence: "证据"
};

export const mappingStatusLabel: Record<MappingStatus, string> = {
  active: "活跃",
  stale: "待复核",
  archived: "归档"
};

export const mappingSourceLabel: Record<MappingSource, string> = {
  manual: "人工配置",
  ai_repository: "AI 仓库推断",
  ai_history: "AI 历史用例推断",
  diff_confirmation: "Diff 分析确认"
};
