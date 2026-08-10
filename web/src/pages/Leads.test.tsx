import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
      { id: "l1", name: "Acme", url: "https://acme.tn", status: "enriched", source: "discovery", lead_score: 42.0, updated_at: null, created_at: null, google_maps_url: null, address: "Tunis", rating: 4.5, review_count: 12, country: "Tunisia", industry: "Logistics", business_type: "SaaS", email: "hi@acme.tn", phone: "+21622", seo_score: 61, status_notes: null, hours: null, description: null, price_level: null, facebook: null, instagram: null, linkedin: null, twitter: null, tags: null },
    ]);
    renderLeads();
    expect(await screen.findByText("Acme")).toBeInTheDocument();
    expect(screen.getByText("enriched", { selector: ".badge" })).toBeInTheDocument();
    expect(screen.getByText("Tunisia")).toBeInTheDocument();
    expect(screen.getByText("Tunis")).toBeInTheDocument();
    expect(screen.getByText("4.5 (12)")).toBeInTheDocument();
    expect(screen.getByText("Logistics")).toBeInTheDocument();
    expect(screen.getByText("SaaS")).toBeInTheDocument();
    expect(screen.getByText("+21622")).toBeInTheDocument();
    expect(screen.getByText("61")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("runs the Lead Completion Agent via the Enrich button", async () => {
    vi.spyOn(leadsApi, "fetchLeads").mockResolvedValue([]);
    const spy = vi.spyOn(leadsApi, "enrichLeads").mockResolvedValue({
      pipeline_run_id: "p1",
      status: "running",
      target_count: 3,
    });
    renderLeads();
    const btn = await screen.findByRole("button", { name: /enrich leads/i });
    fireEvent.click(btn);
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/enrich started/i)).toBeInTheDocument();
  });
});
