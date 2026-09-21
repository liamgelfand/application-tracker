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

/* Desaturated to sit on the warm ink background without the neon-dashboard
   look, while keeping each stage distinguishable at a glance. */
export const STATUS_COLORS: Record<ApplicationStatus, string> = {
  saved:              "#6b645c",   /* warm grey  — neutral, not started */
  applied:            "#5b8cab",   /* dusty blue — submitted */
  online_assessment:  "#8878b4",   /* muted iris — take-home / coding test */
  phone_screen:       "#4f9a8f",   /* soft teal  — live recruiter call */
  interview:          "#d2954a",   /* ochre      — active process */
  offer:              "#7aa35f",   /* moss       — positive outcome */
  rejected:           "#b8564f",   /* brick      — closed negative */
  ghosted:            "#46423c",   /* dark warm  — silent */
  accepted:           "#5f9150",   /* deep moss  — accepted offer */
};

/** Columns hidden on the dashboard unless changed in Settings. */
export const DEFAULT_HIDDEN_BOARD_STATUSES: ApplicationStatus[] = [
  "phone_screen",
  "rejected",
  "ghosted",
];
