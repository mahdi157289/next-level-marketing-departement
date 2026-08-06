import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("applies the status value as class", () => {
    render(<StatusBadge status="success" />);
    expect(screen.getByText("success")).toHaveClass("badge success");
  });

  it("renders an em dash for null status", () => {
    render(<StatusBadge status={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
