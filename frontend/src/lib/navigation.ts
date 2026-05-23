import { ClipboardCheck, FileText, GitBranch, LayoutDashboard, ShieldCheck, Users } from "lucide-react";

export const navItems = [
  { key: "workbench", label: "工作台", icon: LayoutDashboard },
  { key: "projects", label: "项目", icon: GitBranch },
  { key: "library", label: "用例库", icon: ClipboardCheck },
  { key: "reviews", label: "评审", icon: Users },
  { key: "reports", label: "报告", icon: FileText },
  { key: "settings", label: "设置", icon: ShieldCheck }
] as const;

export type NavKey = (typeof navItems)[number]["key"];
