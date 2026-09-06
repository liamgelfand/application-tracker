import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Application } from "../api/types";
import { STATUS_LABELS } from "../lib/statuses";
import StatusBadge from "../components/StatusBadge";

function daysSince(iso: string): number {
  const then = new Date(iso).getTime();
  const ms = Date.now() - then;
  return Math.max(0, Math.floor(ms / (1000 * 60 * 60 * 24)));
}

export default function FollowUps() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: reminders = [], isLoading } = useQuery({
    queryKey: ["reminders"],
    queryFn: () => api.listReminders(),
    refetchInterval: 60000,
  });

  const { data: settings } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.getSettings(),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["reminders"] });
    queryClient.invalidateQueries({ queryKey: ["applications"] });
    queryClient.invalidateQueries({ queryKey: ["analytics"] });
  };

  const ghostOne = useMutation({
    mutationFn: (id: number) =>
      api.updateStatus(id, "ghosted", "Marked ghosted from Follow-ups"),
    onSuccess: invalidate,
  });

  const ghostAll = useMutation({
    mutationFn: async (apps: Application[]) => {
      for (const app of apps) {
        await api.updateStatus(app.id, "ghosted", "Marked ghosted from Follow-ups");
      }
    },
    onSuccess: invalidate,
  });

  const threshold = settings?.follow_up_days ?? 14;

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Follow-ups</h1>
          <p className="subtitle">
            Applications in Applied / Online Assessment / Phone Screen /
            Interview with no update for {threshold}+ days.
          </p>
        </div>
        {reminders.length > 0 && (
          <button
            className="btn-danger"
            disabled={ghostAll.isPending}
            onClick={() => {
              if (
                confirm(
                  `Mark all ${reminders.length} follow-up application(s) as Ghosted?`
                )
              ) {
                ghostAll.mutate(reminders);
              }
            }}
          >
            {ghostAll.isPending ? "Updating…" : "Mark all ghosted"}
          </button>
        )}
      </div>

      {isLoading ? (
        <div className="empty">Loading...</div>
      ) : reminders.length === 0 ? (
        <div className="empty">
          <p>No follow-ups due.</p>
          <p className="muted">
            When an application sits without a reply past your reminder window,
            it will show up here.
          </p>
        </div>
      ) : (
        <div className="card" style={{ padding: 0 }}>
          <table>
            <thead>
              <tr>
                <th>Company</th>
                <th>Title</th>
                <th>Status</th>
                <th>Last update</th>
                <th>Quiet for</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {reminders.map((app) => (
                <tr key={app.id}>
                  <td>
                    <Link to={`/applications/${app.id}`}>{app.company}</Link>
                  </td>
                  <td
                    style={{ cursor: "pointer" }}
                    onClick={() => navigate(`/applications/${app.id}`)}
                  >
                    {app.title}
                  </td>
                  <td>
                    <StatusBadge status={app.status} />
                  </td>
                  <td className="muted">
                    {new Date(app.updated_at).toLocaleDateString()}
                  </td>
                  <td className="muted">{daysSince(app.updated_at)} days</td>
                  <td style={{ textAlign: "right" }}>
                    <button
                      className="btn-secondary"
                      disabled={ghostOne.isPending}
                      onClick={(e) => {
                        e.stopPropagation();
                        ghostOne.mutate(app.id);
                      }}
                      title={`Mark ${STATUS_LABELS.ghosted}`}
                    >
                      Mark ghosted
                    </button>
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
