import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";

type EditForm = {
  company: string;
  title: string;
  location: string;
  url: string;
  source: string;
  salary: string;
  contact_email: string;
  job_id: string;
  skills: string;
  description: string;
  notes: string;
};

function formFromApp(app: {
  company: string;
  title: string;
  location: string | null;
  url: string | null;
  source: string | null;
  salary: string | null;
  contact_email: string | null;
  job_id: string | null;
  skills: string | null;
  description: string | null;
  notes: string | null;
}): EditForm {
  return {
    company: app.company ?? "",
    title: app.title ?? "",
    location: app.location ?? "",
    url: app.url ?? "",
    source: app.source ?? "",
    salary: app.salary ?? "",
    contact_email: app.contact_email ?? "",
    job_id: app.job_id ?? "",
    skills: app.skills ?? "",
    description: app.description ?? "",
    notes: app.notes ?? "",
  };
}

export default function EditApplication() {
  const { id } = useParams();
  const appId = Number(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<EditForm | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: app, isLoading } = useQuery({
    queryKey: ["application", appId],
    queryFn: () => api.getApplication(appId),
    enabled: !!appId,
  });

  useEffect(() => {
    if (app) setForm(formFromApp(app));
  }, [app?.id, app?.updated_at]);

  const saveMutation = useMutation({
    mutationFn: () => {
      if (!form) throw new Error("Nothing to save");
      return api.updateApplication(appId, {
        company: form.company.trim() || "Unknown",
        title: form.title.trim() || "Unknown",
        location: form.location.trim() || null,
        url: form.url.trim() || null,
        source: form.source.trim() || null,
        salary: form.salary.trim() || null,
        contact_email: form.contact_email.trim() || null,
        job_id: form.job_id.trim() || null,
        skills: form.skills.trim() || null,
        description: form.description.trim() || null,
        notes: form.notes,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["application", appId] });
      queryClient.invalidateQueries({ queryKey: ["applications"] });
      queryClient.invalidateQueries({ queryKey: ["reminders"] });
      navigate(`/applications/${appId}`);
    },
    onError: (e: Error) => setError(e.message),
  });

  const set = (key: keyof EditForm, value: string) =>
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));

  if (isLoading || !form) return <div className="empty">Loading...</div>;

  return (
    <div>
      <div className="page-header">
        <div>
          <button
            className="btn-ghost"
            onClick={() => navigate(`/applications/${appId}`)}
          >
            ← Cancel
          </button>
          <h1 className="page-title" style={{ marginTop: 6 }}>
            Edit application
          </h1>
          <p className="subtitle">
            Fix company, title, and other fields, then save.
          </p>
        </div>
        <button
          className="btn-primary"
          disabled={saveMutation.isPending}
          onClick={() => saveMutation.mutate()}
        >
          {saveMutation.isPending ? "Saving…" : "Save changes"}
        </button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="card" style={{ maxWidth: 720 }}>
        <div className="row" style={{ gap: 10 }}>
          <div className="field" style={{ flex: 1, margin: 0 }}>
            <label>Company</label>
            <input
              value={form.company}
              onChange={(e) => set("company", e.target.value)}
            />
          </div>
          <div className="field" style={{ flex: 1, margin: 0 }}>
            <label>Title</label>
            <input
              value={form.title}
              onChange={(e) => set("title", e.target.value)}
              placeholder="e.g. Software Engineer"
            />
          </div>
        </div>
        <div className="row" style={{ gap: 10, marginTop: 10 }}>
          <div className="field" style={{ flex: 1, margin: 0 }}>
            <label>Location</label>
            <input
              value={form.location}
              onChange={(e) => set("location", e.target.value)}
            />
          </div>
          <div className="field" style={{ flex: 1, margin: 0 }}>
            <label>Salary</label>
            <input
              value={form.salary}
              onChange={(e) => set("salary", e.target.value)}
            />
          </div>
        </div>
        <div className="row" style={{ gap: 10, marginTop: 10 }}>
          <div className="field" style={{ flex: 1, margin: 0 }}>
            <label>Source</label>
            <input
              value={form.source}
              onChange={(e) => set("source", e.target.value)}
              placeholder="LinkedIn, company site…"
            />
          </div>
          <div className="field" style={{ flex: 1, margin: 0 }}>
            <label>Contact email</label>
            <input
              value={form.contact_email}
              onChange={(e) => set("contact_email", e.target.value)}
            />
          </div>
        </div>
        <div className="field" style={{ marginTop: 10 }}>
          <label>Job / req ID</label>
          <input
            value={form.job_id}
            onChange={(e) => set("job_id", e.target.value)}
            placeholder="e.g. 128506 — distinguishes multiple roles at one company"
          />
        </div>
        <div className="field" style={{ marginTop: 10 }}>
          <label>Listing URL</label>
          <input
            value={form.url}
            onChange={(e) => set("url", e.target.value)}
            placeholder="https://…"
          />
        </div>
        <div className="field" style={{ marginTop: 10 }}>
          <label>Skills (comma-separated)</label>
          <input
            value={form.skills}
            onChange={(e) => set("skills", e.target.value)}
          />
        </div>
        <div className="field" style={{ marginTop: 10 }}>
          <label>Description</label>
          <textarea
            value={form.description}
            onChange={(e) => set("description", e.target.value)}
            placeholder="Job description / notes from the listing…"
            rows={5}
          />
        </div>
        <div className="field" style={{ marginTop: 10 }}>
          <label>Private notes</label>
          <textarea
            value={form.notes}
            onChange={(e) => set("notes", e.target.value)}
            placeholder="Add private notes about this application..."
            rows={4}
          />
        </div>
        <div className="modal-actions" style={{ marginTop: 16 }}>
          <button
            className="btn-secondary"
            onClick={() => navigate(`/applications/${appId}`)}
          >
            Cancel
          </button>
          <button
            className="btn-primary"
            disabled={saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            {saveMutation.isPending ? "Saving…" : "Save changes"}
          </button>
        </div>
      </div>
    </div>
  );
}
