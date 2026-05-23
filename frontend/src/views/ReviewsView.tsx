import type { Session } from "../api";
import { CaseReviewAdmin } from "./CaseReviewAdmin";

export function ReviewsView({ session }: { session: Session }) {
  return (
    <div className="view-panel">
      <div className="view-panel-body">
        <CaseReviewAdmin session={session} />
      </div>
    </div>
  );
}
