import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { ApplicationStatus } from "../api/types";
import { STATUSES, STATUS_COLORS, STATUS_LABELS } from "../lib/statuses";

function StatCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="card stat-card">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {hint && <div className="muted stat-hint">{hint}</div>}
    </div>
  );
}

export default function Analytics() {
  const { data, isLoading } = useQuery({
    queryKey: ["analytics"],
    queryFn: () => api.getAnalytics(),
  });

  if (isLoading || !data) return <div className="empty">Loading...</div>;

  const maxStatus = Math.max(1, ...Object.values(data.status_counts));
  const maxWeek = Math.max(1, ...data.over_time.map((w) => w.count));

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Analytics</h1>
          <p className="subtitle">Insights across your job search.</p>
        </div>
      </div>

      {data.total === 0 ? (
        <div className="empty">
          No data yet. Add some applications to see your analytics.
        </div>
      ) : (
        <div className="stack">
          <div className="stat-grid">
            <StatCard label="Total tracked" value={String(data.total)} />
            <StatCard
              label="Active"
              value={String(data.active)}
              hint="Not rejected/ghosted/accepted"
            />
            <StatCard
              label="Response rate"
              value={`${data.response_rate}%`}
              hint="Of submitted applications"
            />
            <StatCard
              label="Interview rate"
              value={`${data.interview_rate}%`}
              hint="Reached phone screen or beyond"
            />
            <StatCard
              label="Offer rate"
              value={`${data.offer_rate}%`}
              hint="Received an offer"
            />
            <StatCard
              label="Avg. days to response"
              value={
                data.avg_days_to_response == null
                  ? "—"
                  : String(data.avg_days_to_response)
              }
            />
          </div>

          <div className="row" style={{ alignItems: "flex-start" }}>
            <div className="card" style={{ flex: 1 }}>
              <strong>By status</strong>
              <div className="stack" style={{ marginTop: 14, gap: 10 }}>
                {STATUSES.map((s: ApplicationStatus) => {
                  const count = data.status_counts[s] ?? 0;
                  return (
                    <div className="bar-row" key={s}>
                      <div className="bar-label">{STATUS_LABELS[s]}</div>
                      <div className="bar-track">
                        <div
                          className="bar-fill"
                          style={{
                            width: `${(count / maxStatus) * 100}%`,
                            background: STATUS_COLORS[s],
                          }}
                        />
                      </div>
                      <div className="bar-value">{count}</div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="card" style={{ flex: 1 }}>
              <strong>Applications per week</strong>
              <div className="week-chart" style={{ marginTop: 18 }}>
                {data.over_time.map((w) => (
                  <div className="week-col" key={w.week} title={`${w.count} on week of ${w.week}`}>
                    <div className="week-bar-wrap">
                      <div
                        className="week-bar"
                        style={{ height: `${(w.count / maxWeek) * 100}%` }}
                      />
                    </div>
                    <div className="week-x">
                      {w.week.slice(5)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
