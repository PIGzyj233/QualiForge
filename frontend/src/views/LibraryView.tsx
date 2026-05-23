import { useState } from "react";
import type { Session } from "../api";
import { SubTabs } from "../components/SubTabs";
import { AISuggestionAdmin } from "./AISuggestionAdmin";
import { CaseImportAdmin } from "./CaseImportAdmin";
import { TestPlanAdmin } from "./TestPlanAdmin";

const tabs = [
  { key: "plans", label: "测试计划" },
  { key: "import", label: "导入中心" },
  { key: "ai", label: "智能推荐" }
] as const;

type LibraryTab = (typeof tabs)[number]["key"];

export function LibraryView({ session }: { session: Session }) {
  const [activeTab, setActiveTab] = useState<LibraryTab>("plans");

  return (
    <div className="view-panel">
      <SubTabs tabs={[...tabs]} active={activeTab} onChange={(key) => setActiveTab(key as LibraryTab)} />
      <div className="view-panel-body">
        {activeTab === "plans" ? <TestPlanAdmin session={session} /> : null}
        {activeTab === "import" ? <CaseImportAdmin session={session} /> : null}
        {activeTab === "ai" ? <AISuggestionAdmin session={session} /> : null}
      </div>
    </div>
  );
}
