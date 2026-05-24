import { Bot, ClipboardCheck, FileInput, FileText, GitBranch, LayoutDashboard, Lightbulb, ListChecks, ShieldCheck, Users } from "lucide-react";

export const navItems = [
  { key: "workbench", label: "工作台", icon: LayoutDashboard },
  { key: "agent", label: "Agent", icon: Bot },
  { key: "projects", label: "项目", icon: GitBranch },
  { key: "library", label: "用例库", icon: ClipboardCheck },
  { key: "reviews", label: "评审队列", icon: Users },
  { key: "plans", label: "测试计划", icon: ListChecks },
  { key: "imports", label: "导入中心", icon: FileInput },
  { key: "ai", label: "智能推荐", icon: Lightbulb },
  { key: "reports", label: "报告", icon: FileText },
  { key: "settings", label: "设置", icon: ShieldCheck }
] as const;

export type NavKey = (typeof navItems)[number]["key"];
