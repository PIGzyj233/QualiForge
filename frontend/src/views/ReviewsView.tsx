import type { Session } from "../api";
import { ReviewQueueView } from "./ReviewQueueView";

export function ReviewsView({ session }: { session: Session }) {
  return <ReviewQueueView session={session} />;
}
