import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { ApplicationStatus, Suggestion } from "../api/types";
import { STATUSES, STATUS_LABELS } from "../lib/statuses";

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

type Draft = {
  company: string;
  title: string;
  suggested_status: ApplicationStatus | "";
};

function emailDateLabel(s: Suggestion): string | null {
  const raw = s.email_date ?? s.created_at;
  if (!raw) return null;
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: d.getFullYear() === new Date().getFullYear() ? undefined : "numeric",
  });
}

function draftFrom(s: Suggestion): Draft {
  return {
    company: s.company ?? "",
    title: s.title ?? "",
    suggested_status: s.suggested_status ?? "",
  };
}

export default function ReviewQueue() {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [drafts, setDrafts] = useState<Record<number, Draft>>({});

  const { data: suggestions = [], isLoading } = useQuery({
    queryKey: ["suggestions", "pending"],
    queryFn: () => api.listSuggestions("pending"),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["suggestions"] });
    queryClient.invalidateQueries({ queryKey: ["applications"] });
    setSelected(new Set());
  };

  const getDraft = (s: Suggestion): Draft => drafts[s.id] ?? draftFrom(s);

  const setDraft = (id: number, patch: Partial<Draft>) => {
    setDrafts((prev) => {
      const base = prev[id] ?? draftFrom(suggestions.find((x) => x.id === id)!);
      return { ...prev, [id]: { ...base, ...patch } };
    });
  };

  const approve = useMutation({
    mutationFn: (s: Suggestion) => {
      const d = getDraft(s);
      return api.approveSuggestion(s.id, {
        company: d.company.trim() || null,
        title: d.title.trim() || null,
        suggested_status: d.suggested_status || null,
      });
    },
    onSuccess: invalidate,
  });
  const reject = useMutation({
    mutationFn: (id: number) => api.rejectSuggestion(id),
    onSuccess: invalidate,
  });
  const bulkApprove = useMutation({
    mutationFn: (ids: number[]) => api.bulkApproveSuggestions(ids),
    onSuccess: invalidate,
  });
  const bulkReject = useMutation({
    mutationFn: (ids: number[]) => api.bulkRejectSuggestions(ids),
    onSuccess: invalidate,
  });

  const toggle = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const allSelected =
    suggestions.length > 0 && selected.size === suggestions.length;

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Review Queue</h1>
          <p className="subtitle">
            Email-detected updates awaiting your approval, oldest email first so
            approving in order rebuilds each timeline correctly. Edit company,
            title, or status before approving.
          </p>
        </div>
        {suggestions.length > 0 && (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              className="btn-secondary"
              onClick={() =>
                setSelected(
                  allSelected
                    ? new Set()
                    : new Set(suggestions.map((s) => s.id))
                )
              }
            >
              {allSelected ? "Clear selection" : "Select all"}
            </button>
            <button
              className="btn-secondary"
              disabled={selected.size === 0 || bulkReject.isPending}
              onClick={() => bulkReject.mutate([...selected])}
            >
              Dismiss selected
            </button>
            <button
              className="btn-primary"
              disabled={selected.size === 0 || bulkApprove.isPending}
              onClick={() => bulkApprove.mutate([...selected])}
            >
              Approve selected
            </button>
          </div>
        )}
      </div>

      {isLoading ? (
        <div className="empty">Loading...</div>
      ) : suggestions.length === 0 ? (
        <div className="empty">
          <p>Nothing to review.</p>
          <p className="muted">
            When monitored inboxes receive job-related emails, suggested updates
            will appear here.
          </p>
        </div>
      ) : (
        <div className="grid-cards">
          {suggestions.map((s) => {
            const d = getDraft(s);
            return (
              <div className="card" key={s.id}>
                <div className="flex-between">
                  <label
                    className="switch-row"
                    style={{ gap: 8, cursor: "pointer" }}
                  >
                    <input
                      type="checkbox"
                      checked={selected.has(s.id)}
                      onChange={() => toggle(s.id)}
                    />
                    <span className="badge">{kindLabel(s)}</span>
                  </label>
                  <span
                    className="muted"
                    style={{ fontSize: 12, display: "flex", gap: 8 }}
                  >
                    {emailDateLabel(s) && <span>{emailDateLabel(s)}</span>}
                    {s.confidence != null && <span>{s.confidence}%</span>}
                  </span>
                </div>

                {s.summary && (
                  <p style={{ marginTop: 12, lineHeight: 1.5 }}>{s.summary}</p>
                )}

                <div className="row" style={{ marginTop: 12, gap: 10 }}>
                  <div className="field" style={{ flex: 1, margin: 0 }}>
                    <label>Company</label>
                    <input
                      value={d.company}
                      onChange={(e) =>
                        setDraft(s.id, { company: e.target.value })
                      }
                      placeholder="Company"
                    />
                  </div>
                  <div className="field" style={{ flex: 1, margin: 0 }}>
                    <label>Title</label>
                    <input
                      value={d.title}
                      onChange={(e) =>
                        setDraft(s.id, { title: e.target.value })
                      }
                      placeholder="Role title"
                    />
                  </div>
                </div>
                <div className="field" style={{ marginTop: 10 }}>
                  <label>Status</label>
                  <select
                    value={d.suggested_status}
                    onChange={(e) =>
                      setDraft(s.id, {
                        suggested_status: e.target
                          .value as ApplicationStatus | "",
                      })
                    }
                  >
                    <option value="">No status change</option>
                    {STATUSES.map((st) => (
                      <option key={st} value={st}>
                        {STATUS_LABELS[st]}
                      </option>
                    ))}
                  </select>
                </div>

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
                    <p
                      className="muted"
                      style={{ fontSize: 12, marginTop: 8, marginBottom: 0 }}
                    >
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
                    onClick={() => approve.mutate(s)}
                    disabled={approve.isPending}
                  >
                    Approve
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
