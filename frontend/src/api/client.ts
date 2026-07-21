import type {
  AppSettings,
  Application,
  ApplicationDetail,
  ApplicationStatus,
  EmailAccount,
  LLMProvider,
  ParsedJob,
  Suggestion,
} from "./types";

const BASE = "/api";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  // Applications
  listApplications: (params?: { status?: string; search?: string }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set("status", params.status);
    if (params?.search) q.set("search", params.search);
    const qs = q.toString();
    return request<Application[]>(`/applications${qs ? `?${qs}` : ""}`);
  },
  getApplication: (id: number) =>
    request<ApplicationDetail>(`/applications/${id}`),
  createApplication: (data: Partial<Application>) =>
    request<Application>("/applications", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateApplication: (id: number, data: Record<string, unknown>) =>
    request<ApplicationDetail>(`/applications/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  updateStatus: (id: number, status: ApplicationStatus, note?: string) =>
    request<ApplicationDetail>(`/applications/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ status, status_note: note }),
    }),
  deleteApplication: (id: number) =>
    request<{ message: string }>(`/applications/${id}`, { method: "DELETE" }),

  // Parse
  parseJob: (text: string) =>
    request<ParsedJob>("/parse", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),

  // Suggestions
  listSuggestions: (status = "pending") =>
    request<Suggestion[]>(`/suggestions?status=${status}`),
  approveSuggestion: (id: number) =>
    request<{ message: string }>(`/suggestions/${id}/approve`, {
      method: "POST",
    }),
  rejectSuggestion: (id: number) =>
    request<{ message: string }>(`/suggestions/${id}/reject`, {
      method: "POST",
    }),

  // Settings + LLM providers
  getSettings: () => request<AppSettings>("/settings"),
  updateSettings: (data: Partial<AppSettings>) =>
    request<AppSettings>("/settings", {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  listProviders: () => request<LLMProvider[]>("/settings/llm-providers"),
  createProvider: (data: Record<string, unknown>) =>
    request<LLMProvider>("/settings/llm-providers", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateProvider: (id: number, data: Record<string, unknown>) =>
    request<LLMProvider>(`/settings/llm-providers/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  activateProvider: (id: number) =>
    request<LLMProvider>(`/settings/llm-providers/${id}/activate`, {
      method: "POST",
    }),
  deleteProvider: (id: number) =>
    request<{ message: string }>(`/settings/llm-providers/${id}`, {
      method: "DELETE",
    }),

  // Email accounts
  listEmailAccounts: () => request<EmailAccount[]>("/email-accounts"),
  createEmailAccount: (data: Record<string, unknown>) =>
    request<EmailAccount>("/email-accounts", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateEmailAccount: (id: number, data: Record<string, unknown>) =>
    request<EmailAccount>(`/email-accounts/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteEmailAccount: (id: number) =>
    request<{ message: string }>(`/email-accounts/${id}`, { method: "DELETE" }),
  testEmailConnection: (data: Record<string, unknown>) =>
    request<{ ok: boolean; message: string }>("/email-accounts/test", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  syncEmailAccount: (id: number) =>
    request<{ ok: boolean; stats: Record<string, number> }>(
      `/email-accounts/${id}/sync`,
      { method: "POST" }
    ),
};
