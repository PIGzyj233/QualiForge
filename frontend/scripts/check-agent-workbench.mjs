import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const source = (path) => readFileSync(join(root, path), "utf8");
const directorySource = (path) =>
  readdirSync(join(root, path))
    .filter((name) => name.endsWith(".ts"))
    .map((name) => source(`${path}/${name}`))
    .join("\n");

const api = directorySource("src/api");
const view = source("src/views/AgentWorkbenchView.tsx");
const router = source("src/routes/AppRouter.tsx");

const checks = [
  {
    label: "Agent navigation renders the workbench",
    pass: router.includes('path="agent/*"') && router.includes("<AgentWorkbenchView")
  },
  {
    label: "Global run list API supports project and status filters",
    pass:
      api.includes("export function listAgentRuns") &&
      api.includes("params.set(\"project_id\"") &&
      api.includes("params.set(\"status\"")
  },
  {
    label: "Execution detail API exposes subagents, budget, approvals, and staged outputs",
    pass:
      api.includes("export type AgentExecutionDetailRecord") &&
      api.includes("subagent_runs: AgentSubagentRunRecord[]") &&
      api.includes("pending_approvals: AgentApprovalRecord[]") &&
      api.includes("budget: AgentRunBudgetRecord") &&
      api.includes("staged_outputs: AgentStagedOutputRecord[]")
  },
  {
    label: "Launcher creates and executes agent runs with budget controls",
    pass:
      view.includes("createAgentConversation") &&
      view.includes("createAgentRun") &&
      view.includes("executeAgentRun") &&
      view.includes("max_wall_time_minutes") &&
      view.includes("max_total_source_chars_sent") &&
      view.includes("max_parallel_subagents")
  },
  {
    label: "Run list and status filter are visible",
    pass:
      view.includes("aria-label=\"Agent run list\"") &&
      view.includes("aria-label=\"Run status filter\"") &&
      view.includes("runsPagination.currentItems.map")
  },
  {
    label: "Detail pane has refresh, resume, cancel, and budget usage controls",
    pass:
      view.includes("handleResume") &&
      view.includes("resumeAgentRun") &&
      view.includes("handleCancel") &&
      view.includes("cancelAgentRun") &&
      view.includes("budgetUsage.source_chars_sent") &&
      view.includes("budgetUsage.parallel_subagents")
  },
  {
    label: "Staged outputs can be accepted or rejected",
    pass:
      view.includes("handleOutputDecision") &&
      view.includes("decideAgentStagedOutput") &&
      view.includes("onClick={() => void handleOutputDecision(output, \"accepted\")}") &&
      view.includes("onClick={() => void handleOutputDecision(output, \"rejected\")}")
  },
  {
    label: "Memory curator, search, versions, and rollback are wired",
    pass:
      view.includes("curateAgentMemory") &&
      view.includes("searchAgentMemory") &&
      view.includes("listAgentMemoryVersions") &&
      view.includes("rollbackAgentMemory")
  },
  {
    label: "Pending approvals can be approved or rejected",
    pass:
      view.includes("detail?.pending_approvals") &&
      view.includes("decideAgentApproval") &&
      view.includes("handleApprovalDecision(approval.id, \"approved\")") &&
      view.includes("handleApprovalDecision(approval.id, \"rejected\")")
  }
];

const failed = checks.filter((check) => !check.pass);
for (const check of checks) {
  console.log(`${check.pass ? "ok" : "not ok"} - ${check.label}`);
}

if (failed.length > 0) {
  console.error(`Agent Workbench focused check failed: ${failed.map((check) => check.label).join("; ")}`);
  process.exit(1);
}
