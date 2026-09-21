import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type {
  Analytics,
  AnalyticsFunnelStep,
  AnalyticsSourceRow,
  AnalyticsCompanyRow,
  ApplicationStatus,
} from "../api/types";
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

function daysLabel(value: number | null): string {
  return value == null ? "—" : String(value);
}

function ofSubmitted(count: number, submitted: number): string {
  return `${count} of ${submitted} submitted`;
}

function Funnel({
  steps,
  submitted,
}: {
  steps: AnalyticsFunnelStep[];
  submitted: number;
}) {
  const max = Math.max(1, submitted);
  return (
    <div className="funnel">
      {steps.map((step, i) => {
        const prev = i > 0 ? steps[i - 1] : null;
        return (
          <div className="funnel-step" key={step.stage}>
            <div className="funnel-meta">
              <span className="funnel-label">{step.label}</span>
              <span className="funnel-count">{step.count}</span>
            </div>
            <div className="funnel-track">
              <div
                className="funnel-fill"
                style={{ width: `${(step.count / max) * 100}%` }}
              />
            </div>
            <div className="funnel-rates">
              {step.stage !== "submitted" && (
                <span>{step.rate}% of submitted</span>
              )}
              {prev && prev.count > 0 && step.conversion != null && (
                <span className="funnel-conversion">
                  {step.conversion}% from {prev.label.toLowerCase()}
                </span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function RateTable({
  rows,
  labelKey,
  labelHeader,
}: {
  rows: (AnalyticsSourceRow | AnalyticsCompanyRow)[];
  labelKey: "source" | "company";
  labelHeader: string;
}) {
  if (rows.length === 0) {
    return <div className="muted" style={{ marginTop: 12 }}>No submitted applications yet.</div>;
  }
  return (
    <div className="analytics-table-wrap">
      <table className="analytics-table">
        <thead>
          <tr>
            <th>{labelHeader}</th>
            <th>Apps</th>
            <th>Response</th>
            <th>OA</th>
            <th>Interview</th>
            <th>Offer</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const label = labelKey === "source"
              ? (row as AnalyticsSourceRow).source
              : (row as AnalyticsCompanyRow).company;
            return (
              <tr key={label}>
                <td>{label}</td>
                <td>{row.submitted}</td>
                <td>{row.response_rate}%</td>
                <td>{row.oa_rate}%</td>
                <td>{row.interview_rate}%</td>
                <td>{row.offer_rate}%</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function withDefaults(data: Analytics): Analytics {
  return {
    ...data,
    submitted: data.submitted ?? 0,
    response_count: data.response_count ?? 0,
    oa_count: data.oa_count ?? 0,
    interview_count: data.interview_count ?? 0,
    offer_count: data.offer_count ?? 0,
    ghost_count: data.ghost_count ?? 0,
    ghost_rate: data.ghost_rate ?? 0,
    oa_rate: data.oa_rate ?? 0,
    avg_days_to_oa: data.avg_days_to_oa ?? null,
    avg_days_to_interview: data.avg_days_to_interview ?? null,
    avg_days_to_offer: data.avg_days_to_offer ?? null,
    funnel: data.funnel ?? [],
    rejection_by_stage: data.rejection_by_stage ?? [],
    by_source: data.by_source ?? [],
    by_company: data.by_company ?? [],
  };
}

export default function Analytics() {
  const { data: raw, isLoading } = useQuery({
    queryKey: ["analytics"],
    queryFn: () => api.getAnalytics(),
  });

  if (isLoading || !raw) return <div className="empty">Loading...</div>;
  const data = withDefaults(raw);
  const expanded = Array.isArray(raw.funnel);

  const maxStatus = Math.max(1, ...Object.values(data.status_counts));
  const maxWeek = Math.max(1, ...data.over_time.map((w) => w.count));
  const maxRejection = Math.max(
    1,
    ...data.rejection_by_stage.map((row) => row.count),
  );
  const rejectionTotal = data.rejection_by_stage.reduce(
    (sum, row) => sum + row.count,
    0,
  );

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Analytics</h1>
          <p className="subtitle">
            Insights across your job search. Rates count every stage an application
            actually reached, even after a later rejection.
          </p>
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
              label="Submitted"
              value={String(data.submitted)}
              hint="Excludes saved leads"
            />
            <StatCard
              label="Active"
              value={String(data.active)}
              hint="Not rejected/ghosted/accepted"
            />
            {expanded && (
              <StatCard
                label="Ghost rate"
                value={`${data.ghost_rate}%`}
                hint={ofSubmitted(data.ghost_count, data.submitted)}
              />
            )}
            <StatCard
              label="Response rate"
              value={`${data.response_rate}%`}
              hint={
                expanded
                  ? ofSubmitted(data.response_count, data.submitted)
                  : "Of submitted applications"
              }
            />
            {expanded && (
              <StatCard
                label="OA rate"
                value={`${data.oa_rate}%`}
                hint={ofSubmitted(data.oa_count, data.submitted)}
              />
            )}
            <StatCard
              label="Interview rate"
              value={`${data.interview_rate}%`}
              hint="Live interview — not OA or HireVue"
            />
            <StatCard
              label="Offer rate"
              value={`${data.offer_rate}%`}
              hint={
                expanded
                  ? ofSubmitted(data.offer_count, data.submitted)
                  : "Received an offer"
              }
            />
          </div>

          {expanded && (
            <div className="stat-grid">
              <StatCard
                label="Avg. days to response"
                value={daysLabel(data.avg_days_to_response)}
                hint="First recruiter reply, OA, or rejection"
              />
              <StatCard
                label="Avg. days to OA"
                value={daysLabel(data.avg_days_to_oa)}
                hint="First coding test / HireVue / assessment"
              />
              <StatCard
                label="Avg. days to interview"
                value={daysLabel(data.avg_days_to_interview)}
                hint="First live interview"
              />
              <StatCard
                label="Avg. days to offer"
                value={daysLabel(data.avg_days_to_offer)}
              />
            </div>
          )}
          {!expanded && (
            <div className="stat-grid">
              <StatCard
                label="Avg. days to response"
                value={daysLabel(data.avg_days_to_response)}
              />
            </div>
          )}

          {data.funnel.length > 0 && (
            <div className="card">
              <strong>Conversion funnel</strong>
              <p className="muted stat-hint" style={{ marginTop: 4 }}>
                Each step is “ever reached.” Online assessments (HireVue, CodeSignal,
                coding tests) are not counted as interviews.
              </p>
              <Funnel steps={data.funnel} submitted={data.submitted} />
            </div>
          )}

          <div className="analytics-grid">
            <div className="card">
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

            <div className="card">
              <strong>Applications per week</strong>
              <div className="week-chart" style={{ marginTop: 18 }}>
                {data.over_time.map((w) => (
                  <div
                    className="week-col"
                    key={w.week}
                    title={`${w.count} on week of ${w.week}`}
                  >
                    <div className="week-bar-wrap">
                      <div
                        className="week-bar"
                        style={{ height: `${(w.count / maxWeek) * 100}%` }}
                      />
                    </div>
                    <div className="week-x">{w.week.slice(5)}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {expanded && (
            <div className="analytics-grid">
              <div className="card">
                <strong>Rejections by last stage</strong>
                <p className="muted stat-hint" style={{ marginTop: 4 }}>
                  {rejectionTotal === 0
                    ? "No rejections yet."
                    : "Where the process stopped before a no."}
                </p>
                {rejectionTotal > 0 && (
                  <div className="stack" style={{ marginTop: 14, gap: 10 }}>
                    {data.rejection_by_stage.map((row) => (
                      <div className="bar-row" key={row.stage}>
                        <div className="bar-label">{STATUS_LABELS[row.stage]}</div>
                        <div className="bar-track">
                          <div
                            className="bar-fill"
                            style={{
                              width: `${(row.count / maxRejection) * 100}%`,
                              background: STATUS_COLORS[row.stage],
                            }}
                          />
                        </div>
                        <div className="bar-value">{row.count}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="card">
                <strong>By source</strong>
                <p className="muted stat-hint" style={{ marginTop: 4 }}>
                  Where applications came from, with outcome rates.
                </p>
                <RateTable
                  rows={data.by_source}
                  labelKey="source"
                  labelHeader="Source"
                />
              </div>
            </div>
          )}

          {expanded && (
            <div className="card">
              <strong>Top companies</strong>
              <p className="muted stat-hint" style={{ marginTop: 4 }}>
                Highest volume first. Interview rate uses the full timeline.
              </p>
              <RateTable
                rows={data.by_company}
                labelKey="company"
                labelHeader="Company"
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
