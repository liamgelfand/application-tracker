import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Application, ApplicationStatus } from "../api/types";
import { STATUSES, STATUS_COLORS, STATUS_LABELS, DEFAULT_HIDDEN_BOARD_STATUSES } from "../lib/statuses";
import StatusBadge from "../components/StatusBadge";

type View = "board" | "table";

function AppCard({
  app,
  onDragStart,
  mergeMode,
  selected,
  onSelect,
}: {
  app: Application;
  onDragStart: (id: number) => void;
  mergeMode: boolean;
  selected: boolean;
  onSelect: (id: number) => void;
}) {
  const navigate = useNavigate();
  return (
    <div
      className={`app-card ${selected ? "app-card-selected" : ""}`}
      draggable={!mergeMode}
      style={{ borderLeftColor: STATUS_COLORS[app.status] }}
      onDragStart={(e) => {
        if (mergeMode) return;
        e.dataTransfer.effectAllowed = "move";
        onDragStart(app.id);
      }}
      onClick={() => {
        if (mergeMode) onSelect(app.id);
        else navigate(`/applications/${app.id}`);
      }}
    >
      {mergeMode && (
        <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>
          {selected ? "Selected for merge" : "Click to select"}
        </div>
      )}
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
  const [mergeMode, setMergeMode] = useState(false);
  const [mergePick, setMergePick] = useState<number[]>([]);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [importMsg, setImportMsg] = useState<string | null>(null);

  const { data: apps = [], isLoading } = useQuery({
    queryKey: ["applications", search],
    queryFn: () => api.listApplications({ search: search || undefined }),
  });

  const { data: reminders = [] } = useQuery({
    queryKey: ["reminders"],
    queryFn: () => api.listReminders(),
    refetchInterval: 120000,
  });

  const { data: settings } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.getSettings(),
  });

  const hiddenStatuses = settings?.hidden_board_statuses ?? DEFAULT_HIDDEN_BOARD_STATUSES;

  const draggedId = useRef<number | null>(null);
  const [dragOver, setDragOver] = useState<ApplicationStatus | null>(null);

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: ApplicationStatus }) =>
      api.updateStatus(id, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["applications"] });
      queryClient.invalidateQueries({ queryKey: ["analytics"] });
      queryClient.invalidateQueries({ queryKey: ["reminders"] });
    },
  });

  const mergeMutation = useMutation({
    mutationFn: ({ source, target }: { source: number; target: number }) =>
      api.mergeApplications(source, target),
    onSuccess: (merged) => {
      setMergePick([]);
      setMergeMode(false);
      setImportMsg(`Merged into ${merged.company} — ${merged.title}`);
      queryClient.invalidateQueries({ queryKey: ["applications"] });
      queryClient.invalidateQueries({ queryKey: ["analytics"] });
      queryClient.invalidateQueries({ queryKey: ["reminders"] });
    },
    onError: (e: Error) => setImportMsg(e.message),
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

  const visibleApps = apps.filter((a) => !hiddenStatuses.includes(a.status));

  const boardStatuses = STATUSES.filter((s) => !hiddenStatuses.includes(s));

  const byStatus = (status: string) =>
    visibleApps.filter((a) => a.status === status);

  const onMergeSelect = (id: number) => {
    setMergePick((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= 2) return [prev[1], id];
      return [...prev, id];
    });
  };

  const runMerge = () => {
    if (mergePick.length !== 2) return;
    const [a, b] = mergePick;
    const source = apps.find((x) => x.id === a);
    const target = apps.find((x) => x.id === b);
    if (!source || !target) return;
    // Keep the one with a real title as the target when possible.
    const sourceIsPlaceholder = !source.title || source.title === "Unknown";
    const targetIsPlaceholder = !target.title || target.title === "Unknown";
    let keep = b;
    let drop = a;
    if (sourceIsPlaceholder && !targetIsPlaceholder) {
      keep = b;
      drop = a;
    } else if (!sourceIsPlaceholder && targetIsPlaceholder) {
      keep = a;
      drop = b;
    }
    if (
      confirm(
        `Merge "${source.company} — ${source.title}" and "${target.company} — ${target.title}"?\n\nKeeping #${keep}, deleting #${drop}.`
      )
    ) {
      mergeMutation.mutate({ source: drop, target: keep });
    }
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="subtitle">
            {visibleApps.length} application
            {visibleApps.length === 1 ? "" : "s"}
            {apps.length !== visibleApps.length ? (
              <>
                {" "}
                ({apps.length - visibleApps.length} hidden) ·{" "}
                <Link to="/settings#board-columns">Column visibility</Link>
              </>
            ) : (
              " tracked"
            )}
          </p>
        </div>
        <div
          style={{
            display: "flex",
            gap: 10,
            flexWrap: "wrap",
            justifyContent: "flex-end",
          }}
        >
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
          <button
            className={mergeMode ? "btn-primary" : "btn-secondary"}
            onClick={() => {
              setMergeMode((m) => !m);
              setMergePick([]);
            }}
          >
            {mergeMode ? "Cancel merge" : "Merge"}
          </button>
          <button className="btn-primary" onClick={() => navigate("/add")}>
            + Add Application
          </button>
        </div>
      </div>

      {reminders.length > 0 && (
        <div className="alert alert-info" style={{ marginBottom: 14 }}>
          <strong>
            {reminders.length} follow-up
            {reminders.length === 1 ? "" : "s"} due
          </strong>
          <span className="muted" style={{ marginLeft: 8 }}>
            <Link to="/follow-ups">Open Follow-ups →</Link>
          </span>
        </div>
      )}

      {mergeMode && (
        <div className="alert alert-info" style={{ marginBottom: 14 }}>
          Select two applications to merge
          {mergePick.length === 2 && (
            <>
              {" — "}
              <button
                className="btn-primary"
                style={{ marginLeft: 8 }}
                disabled={mergeMutation.isPending}
                onClick={runMerge}
              >
                Merge selected
              </button>
            </>
          )}
        </div>
      )}

      {importMsg && (
        <div className="alert alert-info" onClick={() => setImportMsg(null)}>
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
          {boardStatuses.map((status) => {
            const items = byStatus(status);
            return (
              <div
                className={`column ${dragOver === status ? "column-dragover" : ""}`}
                key={status}
                onDragOver={(e) => {
                  if (mergeMode) return;
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
                      mergeMode={mergeMode}
                      selected={mergePick.includes(app.id)}
                      onSelect={onMergeSelect}
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
              {visibleApps.map((app) => (
                <tr
                  key={app.id}
                  onClick={() => {
                    if (mergeMode) onMergeSelect(app.id);
                    else navigate(`/applications/${app.id}`);
                  }}
                  className={
                    mergePick.includes(app.id) ? "row-selected" : undefined
                  }
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
