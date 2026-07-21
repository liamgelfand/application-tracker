import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import StatusBadge from "./StatusBadge";

describe("StatusBadge", () => {
  it("renders the human-readable label", () => {
    render(<StatusBadge status="phone_screen" />);
    expect(screen.getByText("Phone Screen")).toBeInTheDocument();
  });

  it("renders a different label per status", () => {
    render(<StatusBadge status="offer" />);
    expect(screen.getByText("Offer")).toBeInTheDocument();
  });
});
