import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { EmailAccount, LLMProvider } from "../api/types";
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
      "claude-3-5-sonnet-20241022",
      "claude-3-5-haiku-20241022",
      "claude-3-opus-20240229",
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
  const [provider, setProvider] = useState("openai");
  const preset = PROVIDER_PRESETS[provider];
  const [name, setName] = useState("");
  const [model, setModel] = useState(preset.models[0]);
  const [customModel, setCustomModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiBase, setApiBase] = useState(preset.apiBase ?? "");
  const [makeActive, setMakeActive] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () =>
      api.createProvider({
        name: name || preset.label,
        provider,
        model: customModel || model,
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

  const onProviderChange = (p: string) => {
    setProvider(p);
    const ps = PROVIDER_PRESETS[p];
    setModel(ps.models[0]);
    setApiBase(ps.apiBase ?? "");
  };

  return (
    <Modal title="Add LLM Provider" onClose={onClose}>
      {error && <div className="alert alert-error">{error}</div>}
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
            placeholder="sk-..."
          />
        </div>
      )}
      <div className="field">
        <label>API Base URL {preset.needsKey ? "(optional)" : ""}</label>
        <input
          value={apiBase}
          onChange={(e) => setApiBase(e.target.value)}
          placeholder={preset.apiBase ?? "https://..."}
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
          className="btn-primary"
          disabled={create.isPending}
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
          <p className="subtitle">Configure AI providers and monitored inboxes.</p>
        </div>
      </div>

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
                  <div style={{ display: "flex", gap: 8 }}>
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
                  <div style={{ display: "flex", gap: 8 }}>
                    <button
                      className="btn-secondary"
                      disabled={syncAccount.isPending}
                      onClick={() => syncAccount.mutate(a.id)}
                    >
                      {syncAccount.isPending ? "Syncing..." : "Sync Now"}
                    </button>
                    <button
                      className="btn-secondary"
                      title="Clear processed history and re-analyze recent mail. Use if an email was missed."
                      disabled={resetAccount.isPending}
                      onClick={() => {
                        if (confirm("Re-analyze all recent mail for this inbox? This will re-run AI classification on emails already seen.")) {
                          resetAccount.mutate(a.id);
                        }
                      }}
                    >
                      Re-analyze
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

      {/* Preferences */}
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
      </div>

      {showProviderModal && (
        <ProviderModal onClose={() => setShowProviderModal(false)} />
      )}
      {showEmailModal && <EmailModal onClose={() => setShowEmailModal(false)} />}
    </div>
  );
}
