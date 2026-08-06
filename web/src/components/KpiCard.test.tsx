import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { KpiCard } from "./KpiCard";

describe("KpiCard", () => {
  it("renders label and value", () => {
    render(<KpiCard label="Leads" value={42} />);
    expect(screen.getByText("Leads")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("uses the accent class", () => {
    render(<KpiCard label="Rate" value="5%" accent="cyan" />);
    expect(screen.getByText("Rate").parentElement).toHaveClass("kpi-card kpi-cyan");
  });
});
