import type { ApplicationStatus } from "../api/types";

export const STATUSES: ApplicationStatus[] = [
  "saved",
  "applied",
  "online_assessment",
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
  online_assessment: "Online Assessment",
  phone_screen: "Phone Screen",
  interview: "Interview",
  offer: "Offer",
  rejected: "Rejected",
  ghosted: "Ghosted",
  accepted: "Accepted",
};

export const STATUS_COLORS: Record<ApplicationStatus, string> = {
  saved:              "#52525b",   /* zinc-600   — neutral, not started */
  applied:            "#0ea5e9",   /* sky-500    — submitted */
  online_assessment:  "#8b5cf6",   /* violet-500 — take-home / coding test */
  phone_screen:       "#14b8a6",   /* teal-500   — live recruiter call */
  interview:          "#f59e0b",   /* amber-500  — active process */
  offer:              "#22c55e",   /* green-500  — positive outcome */
  rejected:           "#f43f5e",   /* rose-500   — closed negative */
  ghosted:            "#3f3f46",   /* zinc-700   — silent */
  accepted:           "#16a34a",   /* green-600  — accepted offer */
};

/** Columns hidden on the dashboard unless changed in Settings. */
export const DEFAULT_HIDDEN_BOARD_STATUSES: ApplicationStatus[] = [
  "phone_screen",
  "rejected",
  "ghosted",
];
