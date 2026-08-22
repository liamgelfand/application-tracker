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
  saved:        "#52525b",   /* zinc-600   — neutral, not started */
  applied:      "#0ea5e9",   /* sky-500    — submitted */
  phone_screen: "#14b8a6",   /* teal-500   — first contact (matches accent) */
  interview:    "#f59e0b",   /* amber-500  — active process */
  offer:        "#22c55e",   /* green-500  — positive outcome */
  rejected:     "#f43f5e",   /* rose-500   — closed negative */
  ghosted:      "#3f3f46",   /* zinc-700   — silent */
  accepted:     "#16a34a",   /* green-600  — accepted offer */
};
