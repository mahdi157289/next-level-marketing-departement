import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import Leads from "./Leads";
import * as leadsApi from "../api/leads";

function renderLeads() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Leads />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Leads", () => {
  it("renders leads from the api", async () => {
    vi.spyOn(leadsApi, "fetchLeads").mockResolvedValue([
      { id: "l1", name: "Acme", url: "https://acme.tn", status: "raw", source: "discovery", lead_score: 0.0, updated_at: null, created_at: null, country: null, industry: null, business_type: null, email: null, phone: null, seo_score: null, status_notes: null },
    ]);
    renderLeads();
    expect(await screen.findByText("Acme")).toBeInTheDocument();
    expect(screen.getByText("raw", { selector: ".badge" })).toBeInTheDocument();
  });
});
