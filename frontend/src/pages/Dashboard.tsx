import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Application, ApplicationStatus } from "../api/types";
import { STATUSES, STATUS_COLORS, STATUS_LABELS } from "../lib/statuses";
import StatusBadge from "../components/StatusBadge";

type View = "board" | "table";

function AppCard({
  app,
  onDragStart,
}: {
  app: Application;
  onDragStart: (id: number) => void;
}) {
  const navigate = useNavigate();
  return (
    <div
      className="app-card"
      draggable
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = "move";
        onDragStart(app.id);
      }}
      onClick={() => navigate(`/applications/${app.id}`)}
    >
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
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [importMsg, setImportMsg] = useState<string | null>(null);

  const { data: apps = [], isLoading } = useQuery({
    queryKey: ["applications", search],
    queryFn: () => api.listApplications({ search: search || undefined }),
  });

  const draggedId = useRef<number | null>(null);
  const [dragOver, setDragOver] = useState<ApplicationStatus | null>(null);

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: ApplicationStatus }) =>
      api.updateStatus(id, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["applications"] });
      queryClient.invalidateQueries({ queryKey: ["analytics"] });
    },
  });

  const handleDrop = (status: ApplicationStatus) => {
    const id = draggedId.current;
    setDragOver(null);
    draggedId.current = null;
    if (id == null) return;
    const app = apps.find((a) => a.id === id);
    if (app && app.status !== status) {
      statusMutation.mutate({ id, status });
    }
  };

  const importMutation = useMutation({
    mutationFn: (file: File) => api.importApplications(file),
    onSuccess: (res) => {
      setImportMsg(res.message);
      queryClient.invalidateQueries({ queryKey: ["applications"] });
      queryClient.invalidateQueries({ queryKey: ["analytics"] });
    },
    onError: (e: Error) => setImportMsg(e.message),
  });

  const onImportFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) importMutation.mutate(file);
    e.target.value = "";
  };

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
        <div style={{ display: "flex", gap: 10 }}>
          <a className="btn-secondary" href={api.exportUrl("csv")}>
            Export CSV
          </a>
          <a className="btn-secondary" href={api.exportUrl("json")}>
            Export JSON
          </a>
          <button
            className="btn-secondary"
            onClick={() => fileInputRef.current?.click()}
            disabled={importMutation.isPending}
          >
            {importMutation.isPending ? "Importing..." : "Import"}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.json"
            style={{ display: "none" }}
            onChange={onImportFile}
          />
          <button className="btn-primary" onClick={() => navigate("/add")}>
            + Add Application
          </button>
        </div>
      </div>

      {importMsg && (
        <div className="alert alert-info" onAnimationEnd={() => setImportMsg(null)}>
          {importMsg}
        </div>
      )}

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
              <div
                className={`column ${dragOver === status ? "column-dragover" : ""}`}
                key={status}
                onDragOver={(e) => {
                  e.preventDefault();
                  if (dragOver !== status) setDragOver(status);
                }}
                onDragLeave={(e) => {
                  if (!e.currentTarget.contains(e.relatedTarget as Node))
                    setDragOver((s) => (s === status ? null : s));
                }}
                onDrop={() => handleDrop(status)}
              >
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
                    <AppCard
                      key={app.id}
                      app={app}
                      onDragStart={(id) => (draggedId.current = id)}
                    />
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
