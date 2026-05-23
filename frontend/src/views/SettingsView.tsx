import type { Session } from "../api";
import { AIConfigAdmin } from "./AIConfigAdmin";

export function SettingsView({ session }: { session: Session }) {
  return (
    <div className="view-panel">
      <div className="view-panel-body">
        <AIConfigAdmin session={session} />
      </div>
    </div>
  );
}
