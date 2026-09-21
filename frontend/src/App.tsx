import { useEffect, useRef } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api/client";
import Dashboard from "./pages/Dashboard";
import AddApplication from "./pages/AddApplication";
import ApplicationDetail from "./pages/ApplicationDetail";
import EditApplication from "./pages/EditApplication";
import Analytics from "./pages/Analytics";
import ReviewQueue from "./pages/ReviewQueue";
import FollowUps from "./pages/FollowUps";
import Settings from "./pages/Settings";

function SyncToast() {
  const { data: progress } = useQuery({
    queryKey: ["syncProgress"],
    queryFn: () => api.getSyncProgress(),
    refetchInterval: (q) => (q.state.data?.running ? 700 : 5000),
  });

  if (!progress) return null;
  if (!progress.running && progress.phase !== "error") return null;

  return (
    <div
      className={`sync-toast ${progress.phase === "error" ? "sync-toast-error" : ""}`}
    >
      {progress.message || (progress.running ? "Syncing inbox…" : "Sync error")}
      {progress.running && progress.total > 0 && (
        <span>
          {" "}
          ({progress.current}/{progress.total})
        </span>
      )}
    </div>
  );
}

function BrandMark() {
  return (
    <svg className="brand-icon" viewBox="0 0 64 64" aria-hidden="true">
      <rect width="64" height="64" rx="14" fill="#1a1917" />
      <rect x="14" y="37" width="8" height="13" rx="3" fill="#e9e5de" />
      <rect x="29" y="26" width="8" height="24" rx="3" fill="#e9e5de" />
      <rect x="44" y="14" width="8" height="36" rx="3" fill="#c8734a" />
    </svg>
  );
}

function Sidebar() {
  const { data: suggestions } = useQuery({
    queryKey: ["suggestions", "pending"],
    queryFn: () => api.listSuggestions("pending"),
    refetchInterval: 60000,
  });
  const pendingCount = suggestions?.length ?? 0;

  const { data: reminders = [] } = useQuery({
    queryKey: ["reminders"],
    queryFn: () => api.listReminders(),
    refetchInterval: 120000,
  });
  const reminderCount = reminders.length;

  // Notify when new email-detected suggestions appear.
  const prevCount = useRef<number | null>(null);
  useEffect(() => {
    if (prevCount.current !== null && pendingCount > prevCount.current) {
      const delta = pendingCount - prevCount.current;
      if (
        typeof Notification !== "undefined" &&
        Notification.permission === "granted"
      ) {
        new Notification("Job Application Tracker", {
          body: `${delta} new job email${delta === 1 ? "" : "s"} to review.`,
        });
      }
    }
    prevCount.current = pendingCount;
  }, [pendingCount]);

  return (
    <aside className="sidebar">
      <div className="brand">
        <BrandMark />
        AppTracker
      </div>

      <NavLink to="/" end className="nav-link">
        Dashboard
      </NavLink>
      <NavLink to="/add" className="nav-link">
        Add Application
      </NavLink>
      <NavLink to="/analytics" className="nav-link">
        Analytics
      </NavLink>
      <NavLink to="/review" className="nav-link">
        Review Queue
        {pendingCount > 0 && <span className="nav-badge">{pendingCount}</span>}
      </NavLink>
      <NavLink to="/follow-ups" className="nav-link">
        Follow-ups
        {reminderCount > 0 && <span className="nav-badge">{reminderCount}</span>}
      </NavLink>
      <NavLink to="/settings" className="nav-link">
        Settings
      </NavLink>

      <div className="spacer" />
    </aside>
  );
}

export default function App() {
  return (
    <div className="app-shell">
      <Sidebar />
      <main className="content">
        <SyncToast />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/add" element={<AddApplication />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/applications/:id" element={<ApplicationDetail />} />
          <Route path="/applications/:id/edit" element={<EditApplication />} />
          <Route path="/review" element={<ReviewQueue />} />
          <Route path="/follow-ups" element={<FollowUps />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}
