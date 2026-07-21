import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Suggestion } from "../api/types";
import { STATUS_LABELS } from "../lib/statuses";

function kindLabel(s: Suggestion): string {
  switch (s.kind) {
    case "new_application":
      return "New application detected";
    case "status_change":
      return "Status change suggested";
    default:
      return "Job-related note";
  }
}

export default function ReviewQueue() {
  const queryClient = useQueryClient();
  const { data: suggestions = [], isLoading } = useQuery({
    queryKey: ["suggestions", "pending"],
    queryFn: () => api.listSuggestions("pending"),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["suggestions"] });
    queryClient.invalidateQueries({ queryKey: ["applications"] });
  };

  const approve = useMutation({
    mutationFn: (id: number) => api.approveSuggestion(id),
    onSuccess: invalidate,
  });
  const reject = useMutation({
    mutationFn: (id: number) => api.rejectSuggestion(id),
    onSuccess: invalidate,
  });

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Review Queue</h1>
          <p className="subtitle">
            Email-detected updates awaiting your approval.
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="empty">Loading...</div>
      ) : suggestions.length === 0 ? (
        <div className="empty">
          <p>Nothing to review. 🎉</p>
          <p className="muted">
            When monitored inboxes receive job-related emails, suggested updates
            will appear here.
          </p>
        </div>
      ) : (
        <div className="grid-cards">
          {suggestions.map((s) => (
            <div className="card" key={s.id}>
              <div className="flex-between">
                <span className="badge">{kindLabel(s)}</span>
                {s.confidence != null && (
                  <span className="muted" style={{ fontSize: 12 }}>
                    {s.confidence}% confident
                  </span>
                )}
              </div>

              {s.summary && (
                <p style={{ marginTop: 12, lineHeight: 1.5 }}>{s.summary}</p>
              )}

              {s.suggested_status && (
                <div className="alert alert-info" style={{ marginTop: 8 }}>
                  Suggested status: <strong>{STATUS_LABELS[s.suggested_status]}</strong>
                </div>
              )}

              <div
                className="card"
                style={{ background: "var(--bg)", marginTop: 8, padding: 12 }}
              >
                <div style={{ fontSize: 13 }}>
                  <strong>{s.email_subject || "(no subject)"}</strong>
                </div>
                <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
                  {s.email_sender}
                </div>
                {s.email_snippet && (
                  <p className="muted" style={{ fontSize: 12, marginTop: 8, marginBottom: 0 }}>
                    {s.email_snippet.slice(0, 220)}
                    {s.email_snippet.length > 220 ? "…" : ""}
                  </p>
                )}
              </div>

              <div className="modal-actions" style={{ marginTop: 14 }}>
                <button
                  className="btn-secondary"
                  onClick={() => reject.mutate(s.id)}
                  disabled={reject.isPending}
                >
                  Dismiss
                </button>
                <button
                  className="btn-primary"
                  onClick={() => approve.mutate(s.id)}
                  disabled={approve.isPending}
                >
                  Approve
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
