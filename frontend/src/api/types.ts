export type ApplicationStatus =
  | "saved"
  | "applied"
  | "phone_screen"
  | "interview"
  | "offer"
  | "rejected"
  | "ghosted"
  | "accepted";

export interface Application {
  id: number;
  company: string;
  title: string;
  location: string | null;
  url: string | null;
  source: string | null;
  salary: string | null;
  status: ApplicationStatus;
  description: string | null;
  skills: string | null;
  notes: string | null;
  contact_email: string | null;
  date_applied: string | null;
  created_at: string;
  updated_at: string;
}

export interface StatusEvent {
  id: number;
  from_status: ApplicationStatus | null;
  to_status: ApplicationStatus | null;
  note: string | null;
  source: "manual" | "email" | "system";
  created_at: string;
}

export interface ApplicationDetail extends Application {
  events: StatusEvent[];
}

export interface ParsedJob {
  company: string | null;
  title: string | null;
  location: string | null;
  url: string | null;
  salary: string | null;
  source: string | null;
  description: string | null;
  skills: string[];
}

export interface LLMProvider {
  id: number;
  name: string;
  provider: string;
  model: string;
  api_base: string | null;
  is_active: boolean;
  has_api_key: boolean;
  created_at: string;
}

export interface EmailAccount {
  id: number;
  name: string;
  imap_host: string;
  imap_port: number;
  username: string;
  use_ssl: boolean;
  folder: string;
  active: boolean;
  last_synced_at: string | null;
  created_at: string;
}

export type SuggestionKind = "status_change" | "new_application" | "note";
export type SuggestionStatusType = "pending" | "approved" | "rejected";

export interface Suggestion {
  id: number;
  application_id: number | null;
  kind: SuggestionKind;
  status: SuggestionStatusType;
  suggested_status: ApplicationStatus | null;
  summary: string | null;
  confidence: number | null;
  email_subject: string | null;
  email_sender: string | null;
  email_snippet: string | null;
  created_at: string;
}

export interface AppSettings {
  email_poll_interval_seconds: number;
  auto_apply_suggestions: boolean;
}
