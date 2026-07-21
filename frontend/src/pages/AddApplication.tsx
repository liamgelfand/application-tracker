import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { ApplicationStatus, ParsedJob } from "../api/types";
import { STATUSES, STATUS_LABELS } from "../lib/statuses";

interface FormState {
  company: string;
  title: string;
  location: string;
  url: string;
  salary: string;
  source: string;
  description: string;
  skills: string;
  status: ApplicationStatus;
}

const EMPTY: FormState = {
  company: "",
  title: "",
  location: "",
  url: "",
  salary: "",
  source: "",
  description: "",
  skills: "",
  status: "saved",
};

export default function AddApplication() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [raw, setRaw] = useState("");
  const [form, setForm] = useState<FormState>(EMPTY);
  const [error, setError] = useState<string | null>(null);

  const parseMutation = useMutation({
    mutationFn: (text: string) => api.parseJob(text),
    onSuccess: (parsed: ParsedJob) => {
      setError(null);
      setForm((f) => ({
        ...f,
        company: parsed.company ?? f.company,
        title: parsed.title ?? f.title,
        location: parsed.location ?? f.location,
        url: parsed.url ?? f.url,
        salary: parsed.salary ?? f.salary,
        source: parsed.source ?? f.source,
        description: parsed.description ?? f.description,
        skills: parsed.skills.length ? parsed.skills.join(", ") : f.skills,
      }));
    },
    onError: (e: Error) => setError(e.message),
  });

  const saveMutation = useMutation({
    mutationFn: () =>
      api.createApplication({
        company: form.company,
        title: form.title,
        location: form.location || null,
        url: form.url || null,
        salary: form.salary || null,
        source: form.source || null,
        description: form.description || null,
        skills: form.skills || null,
        status: form.status,
      }),
    onSuccess: (app) => {
      queryClient.invalidateQueries({ queryKey: ["applications"] });
      navigate(`/applications/${app.id}`);
    },
    onError: (e: Error) => setError(e.message),
  });

  const set = (key: keyof FormState) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => setForm({ ...form, [key]: e.target.value });

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Add Application</h1>
          <p className="subtitle">
            Paste a job listing to auto-fill, or enter details manually.
          </p>
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="row" style={{ alignItems: "flex-start" }}>
        <div className="card" style={{ flex: 1 }}>
          <label>Paste job listing</label>
          <textarea
            style={{ minHeight: 260 }}
            placeholder="Paste the full job description here, then click Parse..."
            value={raw}
            onChange={(e) => setRaw(e.target.value)}
          />
          <button
            className="btn-primary"
            style={{ marginTop: 12, width: "100%" }}
            disabled={!raw.trim() || parseMutation.isPending}
            onClick={() => parseMutation.mutate(raw)}
          >
            {parseMutation.isPending ? "Parsing with AI..." : "✨ Parse with AI"}
          </button>
          <p className="muted" style={{ fontSize: 12, marginTop: 10 }}>
            Requires an active LLM provider in Settings.
          </p>
        </div>

        <div className="card" style={{ flex: 1.2 }}>
          <div className="row">
            <div className="field">
              <label>Company *</label>
              <input value={form.company} onChange={set("company")} />
            </div>
            <div className="field">
              <label>Title *</label>
              <input value={form.title} onChange={set("title")} />
            </div>
          </div>
          <div className="row">
            <div className="field">
              <label>Location</label>
              <input value={form.location} onChange={set("location")} />
            </div>
            <div className="field">
              <label>Salary</label>
              <input value={form.salary} onChange={set("salary")} />
            </div>
          </div>
          <div className="row">
            <div className="field">
              <label>Source</label>
              <input value={form.source} onChange={set("source")} />
            </div>
            <div className="field">
              <label>Status</label>
              <select value={form.status} onChange={set("status")}>
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {STATUS_LABELS[s]}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="field">
            <label>URL</label>
            <input value={form.url} onChange={set("url")} />
          </div>
          <div className="field">
            <label>Skills (comma separated)</label>
            <input value={form.skills} onChange={set("skills")} />
          </div>
          <div className="field">
            <label>Description</label>
            <textarea value={form.description} onChange={set("description")} />
          </div>
          <button
            className="btn-primary"
            style={{ width: "100%" }}
            disabled={!form.company || !form.title || saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            {saveMutation.isPending ? "Saving..." : "Save Application"}
          </button>
        </div>
      </div>
    </div>
  );
}
