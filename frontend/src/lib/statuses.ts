import type { ApplicationStatus } from "../api/types";

export const STATUSES: ApplicationStatus[] = [
  "saved",
  "applied",
  "phone_screen",
  "interview",
  "offer",
  "rejected",
  "ghosted",
  "accepted",
];

export const STATUS_LABELS: Record<ApplicationStatus, string> = {
  saved: "Saved",
  applied: "Applied",
  phone_screen: "Phone Screen",
  interview: "Interview",
  offer: "Offer",
  rejected: "Rejected",
  ghosted: "Ghosted",
  accepted: "Accepted",
};

export const STATUS_COLORS: Record<ApplicationStatus, string> = {
  saved: "#64748b",
  applied: "#3b82f6",
  phone_screen: "#8b5cf6",
  interview: "#f59e0b",
  offer: "#10b981",
  rejected: "#ef4444",
  ghosted: "#6b7280",
  accepted: "#16a34a",
};
