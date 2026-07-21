import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { ApplicationStatus } from "../api/types";
import { STATUSES, STATUS_LABELS } from "../lib/statuses";
import StatusBadge from "../components/StatusBadge";

export default function ApplicationDetail() {
  const { id } = useParams();
  const appId = Number(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: app, isLoading } = useQuery({
    queryKey: ["application", appId],
    queryFn: () => api.getApplication(appId),
    enabled: !!appId,
  });

  useEffect(() => {
    if (app) setNotes(app.notes ?? "");
  }, [app?.id]);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["application", appId] });
    queryClient.invalidateQueries({ queryKey: ["applications"] });
  };

  const statusMutation = useMutation({
    mutationFn: (status: ApplicationStatus) => api.updateStatus(appId, status),
    onSuccess: invalidate,
    onError: (e: Error) => setError(e.message),
  });

  const notesMutation = useMutation({
    mutationFn: () => api.updateApplication(appId, { notes }),
    onSuccess: invalidate,
    onError: (e: Error) => setError(e.message),
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteApplication(appId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["applications"] });
      navigate("/");
    },
  });

  if (isLoading || !app) return <div className="empty">Loading...</div>;

  const skills = app.skills
    ? app.skills.split(",").map((s) => s.trim()).filter(Boolean)
    : [];

  return (
    <div>
      <div className="page-header">
        <div>
          <button className="btn-ghost" onClick={() => navigate("/")}>
            ← Back
          </button>
          <h1 className="page-title" style={{ marginTop: 6 }}>
            {app.title}
          </h1>
          <p className="subtitle">
            {app.company}
            {app.location ? ` · ${app.location}` : ""}
          </p>
        </div>
        <button
          className="btn-danger"
          onClick={() => {
            if (confirm("Delete this application?")) deleteMutation.mutate();
          }}
        >
          Delete
        </button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="row" style={{ alignItems: "flex-start" }}>
        <div className="stack" style={{ flex: 1.4 }}>
          <div className="card">
            <div className="flex-between" style={{ marginBottom: 14 }}>
              <strong>Status</strong>
              <StatusBadge status={app.status} />
            </div>
            <select
              value={app.status}
              onChange={(e) =>
                statusMutation.mutate(e.target.value as ApplicationStatus)
              }
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {STATUS_LABELS[s]}
                </option>
              ))}
            </select>
          </div>

          <div className="card">
            <strong>Details</strong>
            <div style={{ marginTop: 12 }} className="stack">
              {app.salary && (
                <div className="flex-between">
                  <span className="muted">Salary</span>
                  <span>{app.salary}</span>
                </div>
              )}
              {app.source && (
                <div className="flex-between">
                  <span className="muted">Source</span>
                  <span>{app.source}</span>
                </div>
              )}
              {app.url && (
                <div className="flex-between">
                  <span className="muted">Link</span>
                  <a href={app.url} target="_blank" rel="noreferrer">
                    Open listing
                  </a>
                </div>
              )}
              {app.contact_email && (
                <div className="flex-between">
                  <span className="muted">Contact</span>
                  <span>{app.contact_email}</span>
                </div>
              )}
            </div>
            {skills.length > 0 && (
              <div style={{ marginTop: 14 }}>
                <div className="muted" style={{ marginBottom: 8 }}>
                  Skills
                </div>
                <div className="chips">
                  {skills.map((s) => (
                    <span className="chip" key={s}>
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {app.description && (
              <div style={{ marginTop: 14 }}>
                <div className="muted" style={{ marginBottom: 6 }}>
                  Description
                </div>
                <p style={{ margin: 0, lineHeight: 1.6 }}>{app.description}</p>
              </div>
            )}
          </div>

          <div className="card">
            <strong>Notes</strong>
            <textarea
              style={{ marginTop: 10 }}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Add private notes about this application..."
            />
            <button
              className="btn-secondary"
              style={{ marginTop: 10 }}
              disabled={notesMutation.isPending}
              onClick={() => notesMutation.mutate()}
            >
              {notesMutation.isPending ? "Saving..." : "Save Notes"}
            </button>
          </div>
        </div>

        <div className="card" style={{ flex: 1 }}>
          <strong>Timeline</strong>
          <ul className="timeline" style={{ marginTop: 12 }}>
            {app.events.length === 0 && (
              <li className="muted">No activity yet.</li>
            )}
            {app.events.map((ev) => (
              <li key={ev.id}>
                <div className="flex-between">
                  <span>
                    {ev.from_status && ev.to_status && ev.from_status !== ev.to_status
                      ? `${STATUS_LABELS[ev.from_status]} → ${STATUS_LABELS[ev.to_status]}`
                      : ev.to_status
                      ? STATUS_LABELS[ev.to_status]
                      : "Update"}
                  </span>
                  <span className="pill-source">{ev.source}</span>
                </div>
                {ev.note && (
                  <div className="muted" style={{ marginTop: 4 }}>
                    {ev.note}
                  </div>
                )}
                <div className="time">
                  {new Date(ev.created_at).toLocaleString()}
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
