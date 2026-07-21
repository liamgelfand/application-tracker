import type { ApplicationStatus } from "../api/types";
import { STATUS_COLORS, STATUS_LABELS } from "../lib/statuses";

export default function StatusBadge({ status }: { status: ApplicationStatus }) {
  return (
    <span className="badge">
      <span className="status-dot" style={{ background: STATUS_COLORS[status] }} />
      {STATUS_LABELS[status]}
    </span>
  );
}
