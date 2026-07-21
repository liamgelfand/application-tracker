import { NavLink, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api/client";
import Dashboard from "./pages/Dashboard";
import AddApplication from "./pages/AddApplication";
import ApplicationDetail from "./pages/ApplicationDetail";
import ReviewQueue from "./pages/ReviewQueue";
import Settings from "./pages/Settings";

function Sidebar() {
  const { data: suggestions } = useQuery({
    queryKey: ["suggestions", "pending"],
    queryFn: () => api.listSuggestions("pending"),
    refetchInterval: 60000,
  });
  const pendingCount = suggestions?.length ?? 0;

  return (
    <aside className="sidebar">
      <div className="brand">
        <span>📋</span> AppTracker
      </div>
      <NavLink to="/" end className="nav-link">
        Dashboard
      </NavLink>
      <NavLink to="/add" className="nav-link">
        Add Application
      </NavLink>
      <NavLink to="/review" className="nav-link">
        Review Queue
        {pendingCount > 0 && <span className="nav-badge">{pendingCount}</span>}
      </NavLink>
      <NavLink to="/settings" className="nav-link">
        Settings
      </NavLink>
      <div className="spacer" />
      <a
        href="https://github.com"
        target="_blank"
        rel="noreferrer"
        className="nav-link"
      >
        About
      </a>
    </aside>
  );
}

export default function App() {
  return (
    <div className="app-shell">
      <Sidebar />
      <main className="content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/add" element={<AddApplication />} />
          <Route path="/applications/:id" element={<ApplicationDetail />} />
          <Route path="/review" element={<ReviewQueue />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}
