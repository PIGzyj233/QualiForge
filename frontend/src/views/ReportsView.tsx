import type { Session } from "../api";
import { ReleaseReportAdmin } from "./ReleaseReportAdmin";

export function ReportsView({ session }: { session: Session }) {
  return (
    <div className="view-panel">
      <div className="view-panel-body">
        <ReleaseReportAdmin session={session} />
      </div>
    </div>
  );
}
