import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { ApplicationStatus, EmailAccount, LLMProvider } from "../api/types";
import { DEFAULT_HIDDEN_BOARD_STATUSES, STATUSES, STATUS_COLORS, STATUS_LABELS } from "../lib/statuses";
import Modal from "../components/Modal";

const PROVIDER_PRESETS: Record<
  string,
  { label: string; models: string[]; needsKey: boolean; apiBase?: string }
> = {
  openai: {
    label: "OpenAI",
    models: ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"],
    needsKey: true,
  },
  anthropic: {
    label: "Anthropic (Claude)",
    models: [
      "claude-haiku-4-5",
      "claude-sonnet-4-6",
      "claude-sonnet-5",
      "claude-opus-4-6",
    ],
    needsKey: true,
  },
  gemini: {
    label: "Google Gemini",
    models: ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash-exp"],
    needsKey: true,
  },
  ollama: {
    label: "Ollama (local)",
    models: ["llama3.1", "llama3.2", "mistral", "qwen2.5", "phi3"],
    needsKey: false,
    apiBase: "http://localhost:11434",
  },
};

function ProviderModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [provider, setProvider] = useState("anthropic");
  const preset = PROVIDER_PRESETS[provider];
  const [name, setName] = useState("");
  const [model, setModel] = useState(preset.models[0]);
  const [customModel, setCustomModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiBase, setApiBase] = useState(preset.apiBase ?? "");
  const [makeActive, setMakeActive] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(
    null
  );

  const resolvedModel = customModel.trim() || model;

  const create = useMutation({
    mutationFn: () =>
      api.createProvider({
        name: name || preset.label,
        provider,
        model: resolvedModel,
        api_key: apiKey || null,
        api_base: apiBase || null,
        is_active: makeActive,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["providers"] });
      onClose();
    },
    onError: (e: Error) => setError(e.message),
  });

  const test = useMutation({
    mutationFn: () =>
      api.testProvider({
        provider,
        model: resolvedModel,
        api_key: apiKey || null,
        api_base: apiBase || null,
      }),
    onSuccess: setTestResult,
    onError: (e: Error) => setTestResult({ ok: false, message: e.message }),
  });

  const onProviderChange = (p: string) => {
    setProvider(p);
    const ps = PROVIDER_PRESETS[p];
    setModel(ps.models[0]);
    setCustomModel("");
    setApiBase(ps.apiBase ?? "");
    setTestResult(null);
  };

  return (
    <Modal title="Add LLM Provider" onClose={onClose}>
      {error && <div className="alert alert-error">{error}</div>}
      {testResult && (
        <div className={`alert ${testResult.ok ? "alert-success" : "alert-error"}`}>
          {testResult.message}
        </div>
      )}
      <div className="field">
        <label>Provider</label>
        <select value={provider} onChange={(e) => onProviderChange(e.target.value)}>
          {Object.entries(PROVIDER_PRESETS).map(([key, p]) => (
            <option key={key} value={key}>
              {p.label}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label>Display name (optional)</label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={preset.label}
        />
      </div>
      <div className="field">
        <label>Model</label>
        <select value={model} onChange={(e) => setModel(e.target.value)}>
          {preset.models.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label>Or custom model name</label>
        <input
          value={customModel}
          onChange={(e) => setCustomModel(e.target.value)}
          placeholder="Leave blank to use the selected model"
        />
      </div>
      {preset.needsKey && (
        <div className="field">
          <label>API Key</label>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="sk-ant-..."
          />
        </div>
      )}
      <div className="field">
        <label>API Base URL {preset.needsKey ? "(leave blank for Anthropic/OpenAI)" : ""}</label>
        <input
          value={apiBase}
          onChange={(e) => setApiBase(e.target.value)}
          placeholder={preset.apiBase ?? "leave blank"}
        />
      </div>
      <div className="switch-row">
        <input
          type="checkbox"
          id="makeActive"
          checked={makeActive}
          onChange={(e) => setMakeActive(e.target.checked)}
        />
        <label htmlFor="makeActive" style={{ margin: 0 }}>
          Make this the active provider
        </label>
      </div>
      <div className="modal-actions">
        <button className="btn-secondary" onClick={onClose}>
          Cancel
        </button>
        <button
          className="btn-secondary"
          disabled={test.isPending}
          onClick={() => test.mutate()}
        >
          {test.isPending ? "Testing..." : "Test"}
        </button>
        <button
          className="btn-primary"
          disabled={create.isPending || (testResult !== null && !testResult.ok)}
          onClick={() => create.mutate()}
        >
          {create.isPending ? "Adding..." : "Add Provider"}
        </button>
      </div>
    </Modal>
  );
}

function EmailModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    name: "",
    imap_host: "",
    imap_port: 993,
    username: "",
    password: "",
    use_ssl: true,
    folder: "INBOX",
  });
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(
    null
  );
  const [error, setError] = useState<string | null>(null);

  const set = (k: string, v: unknown) => setForm({ ...form, [k]: v });

  const test = useMutation({
    mutationFn: () => api.testEmailConnection(form),
    onSuccess: setTestResult,
    onError: (e: Error) => setError(e.message),
  });

  const create = useMutation({
    mutationFn: () => api.createEmailAccount(form),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["emailAccounts"] });
      onClose();
    },
    onError: (e: Error) => setError(e.message),
  });

  return (
    <Modal title="Add Email Account (IMAP)" onClose={onClose}>
      {error && <div className="alert alert-error">{error}</div>}
      {testResult && (
        <div className={`alert ${testResult.ok ? "alert-success" : "alert-error"}`}>
          {testResult.message}
        </div>
      )}
      <div className="field">
        <label>Account name</label>
        <input
          value={form.name}
          onChange={(e) => set("name", e.target.value)}
          placeholder="Personal Gmail"
        />
      </div>
      <div className="row">
        <div className="field" style={{ flex: 2 }}>
          <label>IMAP host</label>
          <input
            value={form.imap_host}
            onChange={(e) => set("imap_host", e.target.value)}
            placeholder="imap.gmail.com"
          />
        </div>
        <div className="field">
          <label>Port</label>
          <input
            type="number"
            value={form.imap_port}
            onChange={(e) => set("imap_port", Number(e.target.value))}
          />
        </div>
      </div>
      <div className="field">
        <label>Username / email</label>
        <input
          value={form.username}
          onChange={(e) => set("username", e.target.value)}
        />
      </div>
      <div className="field">
        <label>Password / app password</label>
        <input
          type="password"
          value={form.password}
          onChange={(e) => set("password", e.target.value)}
        />
      </div>
      <div className="row">
        <div className="field">
          <label>Folder</label>
          <input
            value={form.folder}
            onChange={(e) => set("folder", e.target.value)}
          />
        </div>
        <div className="field switch-row" style={{ marginTop: 26 }}>
          <input
            type="checkbox"
            id="useSsl"
            checked={form.use_ssl}
            onChange={(e) => set("use_ssl", e.target.checked)}
          />
          <label htmlFor="useSsl" style={{ margin: 0 }}>
            Use SSL
          </label>
        </div>
      </div>
      <p className="muted" style={{ fontSize: 12 }}>
        Tip: for Gmail/Outlook use an app password, not your login password.
      </p>
      <div className="modal-actions">
        <button
          className="btn-secondary"
          disabled={test.isPending}
          onClick={() => test.mutate()}
        >
          {test.isPending ? "Testing..." : "Test Connection"}
        </button>
        <button
          className="btn-primary"
          disabled={create.isPending}
          onClick={() => create.mutate()}
        >
          {create.isPending ? "Saving..." : "Add Account"}
        </button>
      </div>
    </Modal>
  );
}

function NotificationToggle() {
  const supported = typeof Notification !== "undefined";
  const [permission, setPermission] = useState(
    supported ? Notification.permission : "denied"
  );

  if (!supported) {
    return <span className="muted">Not supported</span>;
  }
  if (permission === "granted") {
    return <span className="badge">Enabled</span>;
  }
  if (permission === "denied") {
    return <span className="muted">Blocked in browser</span>;
  }
  return (
    <button
      className="btn-secondary"
      onClick={async () => setPermission(await Notification.requestPermission())}
    >
      Enable
    </button>
  );
}

export default function Settings() {
  const queryClient = useQueryClient();
  const [showProviderModal, setShowProviderModal] = useState(false);
  const [showEmailModal, setShowEmailModal] = useState(false);

  const { data: providers = [] } = useQuery({
    queryKey: ["providers"],
    queryFn: () => api.listProviders(),
  });
  const { data: accounts = [] } = useQuery({
    queryKey: ["emailAccounts"],
    queryFn: () => api.listEmailAccounts(),
  });
  const { data: settings } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.getSettings(),
  });

  const activate = useMutation({
    mutationFn: (id: number) => api.activateProvider(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["providers"] }),
  });
  const testSaved = useMutation({
    mutationFn: (id: number) => api.testSavedProvider(id),
    onSuccess: (res) => window.alert(res.message),
    onError: (e: Error) => window.alert(e.message),
  });
  const deleteProvider = useMutation({
    mutationFn: (id: number) => api.deleteProvider(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["providers"] }),
  });
  const deleteAccount = useMutation({
    mutationFn: (id: number) => api.deleteEmailAccount(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["emailAccounts"] }),
  });
  const syncAccount = useMutation({
    mutationFn: (id: number) => api.syncEmailAccount(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["emailAccounts"] });
      queryClient.invalidateQueries({ queryKey: ["suggestions"] });
    },
  });
  const catchUpAccount = useMutation({
    mutationFn: (id: number) => api.catchUpEmailAccount(id, 75),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ["emailAccounts"] });
      queryClient.invalidateQueries({ queryKey: ["suggestions"] });
      window.alert(res.message);
    },
    onError: (e: Error) => window.alert(e.message),
  });
  const resetAccount = useMutation({
    mutationFn: async (id: number) => {
      await api.resetEmailAccount(id);
      return api.syncEmailAccount(id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["emailAccounts"] });
      queryClient.invalidateQueries({ queryKey: ["suggestions"] });
    },
  });
  const { data: syncProgress } = useQuery({
    queryKey: ["syncProgress"],
    queryFn: () => api.getSyncProgress(),
    refetchInterval: (q) => (q.state.data?.running ? 800 : 4000),
  });

  const toggleAutoApply = useMutation({
    mutationFn: (value: boolean) =>
      api.updateSettings({ auto_apply_suggestions: value }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings"] }),
  });
  const setInterval = useMutation({
    mutationFn: (seconds: number) =>
      api.updateSettings({ email_poll_interval_seconds: seconds }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings"] }),
  });
  const setConfidence = useMutation({
    mutationFn: (value: number) =>
      api.updateSettings({ min_suggestion_confidence: value }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings"] }),
  });
  const setFollowUp = useMutation({
    mutationFn: (value: number) =>
      api.updateSettings({ follow_up_days: value }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      queryClient.invalidateQueries({ queryKey: ["reminders"] });
    },
  });
  const setHiddenColumns = useMutation({
    mutationFn: (hidden: ApplicationStatus[]) =>
      api.updateSettings({ hidden_board_statuses: hidden }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      queryClient.invalidateQueries({ queryKey: ["applications"] });
    },
  });

  const INTERVAL_OPTIONS = [
    { label: "Every 5 minutes", value: 300 },
    { label: "Every 15 minutes", value: 900 },
    { label: "Every 30 minutes", value: 1800 },
    { label: "Every hour", value: 3600 },
    { label: "Every 2 hours", value: 7200 },
  ];

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Settings</h1>
          <p className="subtitle">Configure AI providers, inboxes, and the dashboard.</p>
        </div>
      </div>

      {(syncProgress?.running || syncProgress?.phase === "done" || syncProgress?.phase === "error") && (
        <div
          className={`alert ${syncProgress.phase === "error" ? "alert-error" : "alert-info"}`}
          style={{ marginBottom: 16 }}
        >
          {syncProgress.running
            ? syncProgress.message || "Syncing…"
            : syncProgress.message}
          {syncProgress.running && syncProgress.total > 0 && (
            <span className="muted" style={{ marginLeft: 8 }}>
              ({syncProgress.current}/{syncProgress.total})
            </span>
          )}
        </div>
      )}

      {/* LLM providers */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="flex-between" style={{ marginBottom: 14 }}>
          <div>
            <strong>AI Providers</strong>
            <p className="muted" style={{ margin: "4px 0 0", fontSize: 13 }}>
              Add multiple providers and toggle the active one anytime.
            </p>
          </div>
          <button className="btn-primary" onClick={() => setShowProviderModal(true)}>
            + Add Provider
          </button>
        </div>
        <div className="alert alert-info" style={{ marginBottom: 14 }}>
          <strong>Cloud tip:</strong> Local Ollama is free but slow on CPU. For
          faster email analysis, add OpenAI (<code>gpt-4o-mini</code>) or
          Anthropic (<code>claude-3-5-haiku</code>) with your own API key — typically
          a few cents per inbox sync.
        </div>
        {providers.length === 0 ? (
          <p className="muted">
            No providers yet. Add one to enable job parsing and email analysis.
          </p>
        ) : (
          <div className="stack">
            {providers.map((p: LLMProvider) => (
              <div
                key={p.id}
                className="card"
                style={{ background: "var(--bg)", padding: 14 }}
              >
                <div className="flex-between">
                  <div>
                    <strong>{p.name}</strong>{" "}
                    {p.is_active && (
                      <span
                        className="badge"
                        style={{ borderColor: "var(--success)", marginLeft: 6 }}
                      >
                        Active
                      </span>
                    )}
                    <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
                      {p.provider} · {p.model}
                      {p.has_api_key ? " · key saved" : ""}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <button
                      className="btn-secondary"
                      disabled={testSaved.isPending}
                      onClick={() => testSaved.mutate(p.id)}
                    >
                      {testSaved.isPending ? "Testing..." : "Test"}
                    </button>
                    {!p.is_active && (
                      <button
                        className="btn-secondary"
                        onClick={() => activate.mutate(p.id)}
                      >
                        Set Active
                      </button>
                    )}
                    <button
                      className="btn-danger"
                      onClick={() => deleteProvider.mutate(p.id)}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Email accounts */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="flex-between" style={{ marginBottom: 14 }}>
          <div>
            <strong>Monitored Inboxes</strong>
            <p className="muted" style={{ margin: "4px 0 0", fontSize: 13 }}>
              IMAP inboxes checked in the background for job-related emails.
            </p>
          </div>
          <button className="btn-primary" onClick={() => setShowEmailModal(true)}>
            + Add Inbox
          </button>
        </div>
        {accounts.length === 0 ? (
          <p className="muted">No inboxes connected.</p>
        ) : (
          <div className="stack">
            {accounts.map((a: EmailAccount) => (
              <div
                key={a.id}
                className="card"
                style={{ background: "var(--bg)", padding: 14 }}
              >
                <div className="flex-between">
                  <div>
                    <strong>{a.name}</strong>
                    <div className="muted" style={{ fontSize: 13, marginTop: 4 }}>
                      {a.username} · {a.imap_host}
                    </div>
                    <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
                      {a.last_synced_at
                        ? `Last synced ${new Date(a.last_synced_at).toLocaleString()}`
                        : "Not synced yet"}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <button
                      className="btn-secondary"
                      disabled={syncAccount.isPending}
                      onClick={() => syncAccount.mutate(a.id)}
                    >
                      {syncAccount.isPending ? "Syncing..." : "Sync Now"}
                    </button>
                    <button
                      className="btn-primary"
                      title="Re-scan recent mail. Already-classified emails are skipped (no Claude cost)."
                      disabled={catchUpAccount.isPending}
                      onClick={() => catchUpAccount.mutate(a.id)}
                    >
                      {catchUpAccount.isPending ? "Catching up…" : "Catch up missed"}
                    </button>
                    <button
                      className="btn-secondary"
                      title="Deletes the last 10 processed markers and re-runs Claude on them. Costs credits."
                      disabled={resetAccount.isPending}
                      onClick={() => {
                        if (
                          confirm(
                            "Re-analyze the last 10 emails with Claude again? This spends API credits on mail you already classified. Prefer Catch up missed if you only need gaps."
                          )
                        ) {
                          resetAccount.mutate(a.id);
                        }
                      }}
                    >
                      Re-analyze (costs credits)
                    </button>
                    <button
                      className="btn-danger"
                      onClick={() => deleteAccount.mutate(a.id)}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card" id="board-columns" style={{ marginBottom: 20 }}>
        <strong>Dashboard columns</strong>
        <p className="muted" style={{ margin: "6px 0 0", fontSize: 13 }}>
          Choose which statuses appear on the board and table. Hidden columns stay
          in the tracker, analytics, and follow-ups.
        </p>
        <div className="board-column-picker">
          {STATUSES.map((status) => {
            const hidden =
              settings?.hidden_board_statuses ?? DEFAULT_HIDDEN_BOARD_STATUSES;
            const shown = !hidden.includes(status);
            const visibleCount = STATUSES.length - hidden.length;
            return (
              <label className="board-column-option" key={status}>
                <input
                  type="checkbox"
                  checked={shown}
                  disabled={shown && visibleCount <= 1}
                  onChange={(e) => {
                    const next = e.target.checked
                      ? hidden.filter((s) => s !== status)
                      : [...hidden, status];
                    setHiddenColumns.mutate(next);
                  }}
                />
                <span
                  className="status-dot"
                  style={{ background: STATUS_COLORS[status] }}
                />
                {STATUS_LABELS[status]}
              </label>
            );
          })}
        </div>
      </div>

      <div className="card">
        <strong>Preferences</strong>
        <div className="flex-between" style={{ marginTop: 14 }}>
          <div>
            <div>Desktop notifications</div>
            <p className="muted" style={{ margin: "4px 0 0", fontSize: 13 }}>
              Get a browser notification when new job emails land in the review
              queue.
            </p>
          </div>
          <NotificationToggle />
        </div>
        <hr style={{ border: "none", borderTop: "1px solid var(--border)", margin: "16px 0 0" }} />
        <div className="flex-between" style={{ marginTop: 14 }}>
          <div>
            <div>Auto-apply email suggestions</div>
            <p className="muted" style={{ margin: "4px 0 0", fontSize: 13 }}>
              When on, detected updates are applied automatically instead of waiting
              in the review queue.
            </p>
          </div>
          <label className="switch-row">
            <input
              type="checkbox"
              checked={settings?.auto_apply_suggestions ?? false}
              onChange={(e) => toggleAutoApply.mutate(e.target.checked)}
            />
          </label>
        </div>
        <div className="flex-between" style={{ marginTop: 18 }}>
          <div>
            <div>Inbox check frequency</div>
            <p className="muted" style={{ margin: "4px 0 0", fontSize: 13 }}>
              How often monitored inboxes are automatically checked in the
              background. No need to press Sync Now.
            </p>
          </div>
          <select
            style={{ maxWidth: 200 }}
            value={settings?.email_poll_interval_seconds ?? 900}
            onChange={(e) => setInterval.mutate(Number(e.target.value))}
          >
            {INTERVAL_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
            {settings &&
              !INTERVAL_OPTIONS.some(
                (o) => o.value === settings.email_poll_interval_seconds
              ) && (
                <option value={settings.email_poll_interval_seconds}>
                  Every {settings.email_poll_interval_seconds} seconds
                </option>
              )}
          </select>
        </div>
        <div className="flex-between" style={{ marginTop: 18 }}>
          <div>
            <div>Minimum suggestion confidence</div>
            <p className="muted" style={{ margin: "4px 0 0", fontSize: 13 }}>
              Emails below this score are marked processed but skipped — no
              review-queue item is created.
            </p>
          </div>
          <select
            style={{ maxWidth: 140 }}
            value={settings?.min_suggestion_confidence ?? 70}
            onChange={(e) => setConfidence.mutate(Number(e.target.value))}
          >
            {[50, 60, 70, 80, 90].map((v) => (
              <option key={v} value={v}>
                {v}%
              </option>
            ))}
          </select>
        </div>
        <div className="flex-between" style={{ marginTop: 18 }}>
          <div>
            <div>Follow-up reminder after</div>
            <p className="muted" style={{ margin: "4px 0 0", fontSize: 13 }}>
              Highlight Applied / Online Assessment / Phone Screen / Interview
              apps with no update for this many days.
            </p>
          </div>
          <select
            style={{ maxWidth: 140 }}
            value={settings?.follow_up_days ?? 14}
            onChange={(e) => setFollowUp.mutate(Number(e.target.value))}
          >
            {[7, 10, 14, 21, 30].map((v) => (
              <option key={v} value={v}>
                {v} days
              </option>
            ))}
          </select>
        </div>
      </div>

      {showProviderModal && (
        <ProviderModal onClose={() => setShowProviderModal(false)} />
      )}
      {showEmailModal && <EmailModal onClose={() => setShowEmailModal(false)} />}
    </div>
  );
}
