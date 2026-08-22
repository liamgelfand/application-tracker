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

  const { data: app, isLoading } = useQuery({
    queryKey: ["application", appId],
    queryFn: () => api.getApplication(appId),
    enabled: !!appId,
  });

  const statusMutation = useMutation({
    mutationFn: (status: ApplicationStatus) => api.updateStatus(appId, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["application", appId] });
      queryClient.invalidateQueries({ queryKey: ["applications"] });
      queryClient.invalidateQueries({ queryKey: ["reminders"] });
    },
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
        <div style={{ display: "flex", gap: 8 }}>
          <button
            className="btn-primary"
            onClick={() => navigate(`/applications/${appId}/edit`)}
          >
            Edit
          </button>
          <button
            className="btn-danger"
            onClick={() => {
              if (confirm("Delete this application?")) deleteMutation.mutate();
            }}
          >
            Delete
          </button>
        </div>
      </div>

      {statusMutation.isError && (
        <div className="alert alert-error">
          {(statusMutation.error as Error).message}
        </div>
      )}

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
              <div className="flex-between">
                <span className="muted">Company</span>
                <span>{app.company}</span>
              </div>
              <div className="flex-between">
                <span className="muted">Title</span>
                <span>{app.title}</span>
              </div>
              {app.job_id && (
                <div className="flex-between">
                  <span className="muted">Job / req ID</span>
                  <span>{app.job_id}</span>
                </div>
              )}
              {app.location && (
                <div className="flex-between">
                  <span className="muted">Location</span>
                  <span>{app.location}</span>
                </div>
              )}
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
            <strong>Private notes</strong>
            {app.notes ? (
              <p style={{ marginTop: 10, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
                {app.notes}
              </p>
            ) : (
              <p className="muted" style={{ marginTop: 10 }}>
                No notes yet. Use Edit to add some.
              </p>
            )}
          </div>
        </div>

        <div className="stack" style={{ flex: 1 }}>
          <div className="card">
            <strong>Status timeline</strong>
            <ul className="timeline" style={{ marginTop: 12 }}>
              {app.events.length === 0 && (
                <li className="muted">No activity yet.</li>
              )}
              {app.events.map((ev) => (
                <li key={ev.id}>
                  <div className="flex-between">
                    <span>
                      {ev.from_status &&
                      ev.to_status &&
                      ev.from_status !== ev.to_status
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

          <div className="card">
            <strong>Email timeline</strong>
            <p className="muted" style={{ fontSize: 13, margin: "6px 0 0" }}>
              Related inbox messages for {app.company}.
            </p>
            <ul className="timeline" style={{ marginTop: 12 }}>
              {(app.related_emails?.length ?? 0) === 0 && (
                <li className="muted">No related emails yet.</li>
              )}
              {(app.related_emails ?? []).map((em) => (
                <li key={`${em.kind}-${em.id}`}>
                  <div className="flex-between">
                    <span style={{ fontWeight: 600 }}>
                      {em.subject || "(no subject)"}
                    </span>
                    <span className="pill-source">
                      {em.kind === "suggestion" ? "suggestion" : "email"}
                    </span>
                  </div>
                  {em.sender && (
                    <div className="muted" style={{ marginTop: 2, fontSize: 12 }}>
                      {em.sender}
                    </div>
                  )}
                  {(em.summary || em.snippet) && (
                    <div className="muted" style={{ marginTop: 4 }}>
                      {(em.summary || em.snippet || "").slice(0, 200)}
                    </div>
                  )}
                  <div className="time">
                    {new Date(em.created_at).toLocaleString()}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
