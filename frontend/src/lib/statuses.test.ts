import { describe, expect, it } from "vitest";
import { STATUSES, STATUS_COLORS, STATUS_LABELS } from "./statuses";

describe("statuses", () => {
  it("has 8 pipeline stages", () => {
    expect(STATUSES).toHaveLength(8);
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
});
