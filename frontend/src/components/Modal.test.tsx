import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import Modal from "./Modal";

describe("Modal", () => {
  it("renders the title and children", () => {
    render(
      <Modal title="Add Provider" onClose={() => {}}>
        <p>Body content</p>
      </Modal>
    );
    expect(screen.getByText("Add Provider")).toBeInTheDocument();
    expect(screen.getByText("Body content")).toBeInTheDocument();
  });

  it("calls onClose when the close button is clicked", async () => {
    const onClose = vi.fn();
    render(
      <Modal title="Title" onClose={onClose}>
        <p>x</p>
      </Modal>
    );
    await userEvent.click(screen.getByText("✕"));
    expect(onClose).toHaveBeenCalledOnce();
  });
});
