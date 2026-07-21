import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Application } from "../api/types";
import { STATUSES, STATUS_COLORS, STATUS_LABELS } from "../lib/statuses";
import StatusBadge from "../components/StatusBadge";

type View = "board" | "table";

function AppCard({ app }: { app: Application }) {
  const navigate = useNavigate();
  return (
    <div className="app-card" onClick={() => navigate(`/applications/${app.id}`)}>
      <h4>{app.title}</h4>
      <div className="company">{app.company}</div>
      {(app.location || app.salary) && (
        <div className="meta">
          {[app.location, app.salary].filter(Boolean).join(" · ")}
        </div>
      )}
    </div>
  );
}

export default function Dashboard() {
  const [view, setView] = useState<View>("board");
  const [search, setSearch] = useState("");
  const navigate = useNavigate();

  const { data: apps = [], isLoading } = useQuery({
    queryKey: ["applications", search],
    queryFn: () => api.listApplications({ search: search || undefined }),
  });

  const byStatus = (status: string) => apps.filter((a) => a.status === status);

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="subtitle">
            {apps.length} application{apps.length === 1 ? "" : "s"} tracked
          </p>
        </div>
        <button className="btn-primary" onClick={() => navigate("/add")}>
          + Add Application
        </button>
      </div>

      <div className="toolbar">
        <input
          className="search"
          placeholder="Search company, title, location..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="spacer" />
        <div className="tabs" style={{ margin: 0 }}>
          <button
            className={`tab ${view === "board" ? "active" : ""}`}
            onClick={() => setView("board")}
          >
            Board
          </button>
          <button
            className={`tab ${view === "table" ? "active" : ""}`}
            onClick={() => setView("table")}
          >
            Table
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="empty">Loading...</div>
      ) : apps.length === 0 ? (
        <div className="empty">
          <p>No applications yet.</p>
          <button className="btn-primary" onClick={() => navigate("/add")}>
            Add your first application
          </button>
        </div>
      ) : view === "board" ? (
        <div className="board">
          {STATUSES.map((status) => {
            const items = byStatus(status);
            return (
              <div className="column" key={status}>
                <div className="column-header">
                  <span
                    className="status-dot"
                    style={{ background: STATUS_COLORS[status] }}
                  />
                  {STATUS_LABELS[status]}
                  <span className="column-count">{items.length}</span>
                </div>
                <div className="column-body">
                  {items.map((app) => (
                    <AppCard key={app.id} app={app} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="card" style={{ padding: 0 }}>
          <table>
            <thead>
              <tr>
                <th>Company</th>
                <th>Title</th>
                <th>Location</th>
                <th>Status</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {apps.map((app) => (
                <tr
                  key={app.id}
                  onClick={() => navigate(`/applications/${app.id}`)}
                >
                  <td>{app.company}</td>
                  <td>{app.title}</td>
                  <td className="muted">{app.location || "—"}</td>
                  <td>
                    <StatusBadge status={app.status} />
                  </td>
                  <td className="muted">
                    {new Date(app.updated_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
