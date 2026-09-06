import { describe, expect, it } from "vitest";
import { STATUSES, STATUS_COLORS, STATUS_LABELS, DEFAULT_HIDDEN_BOARD_STATUSES } from "./statuses";

describe("statuses", () => {
  it("has 9 pipeline stages", () => {
    expect(STATUSES).toHaveLength(9);
  });

  it("has a label and color for every status", () => {
    for (const status of STATUSES) {
      expect(STATUS_LABELS[status]).toBeTruthy();
      expect(STATUS_COLORS[status]).toMatch(/^#[0-9a-f]{6}$/i);
    }
  });

  it("orders saved first and accepted last", () => {
    expect(STATUSES[0]).toBe("saved");
    expect(STATUSES[STATUSES.length - 1]).toBe("accepted");
  });

  it("places online assessment between applied and phone screen", () => {
    expect(STATUSES.indexOf("applied")).toBeLessThan(
      STATUSES.indexOf("online_assessment"),
    );
    expect(STATUSES.indexOf("online_assessment")).toBeLessThan(
      STATUSES.indexOf("phone_screen"),
    );
  });

  it("hides phone screen, rejected, and ghosted by default", () => {
    expect(DEFAULT_HIDDEN_BOARD_STATUSES).toEqual([
      "phone_screen",
      "rejected",
      "ghosted",
    ]);
  });
});
