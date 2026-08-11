import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import LeadsDetail from "./LeadsDetail";
import * as leadsApi from "../api/leads";

function renderDetail(
  research: unknown = {
    summary: "Acme is a logistics SaaS in Tunis.", status: "ok",
    sources: [{ title: "Acme site", url: "https://acme.tn", snippet: "s" }],
  },
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.spyOn(leadsApi, "fetchLead").mockResolvedValue({
    id: "l1", name: "Acme", url: "https://acme.tn", status: "enriched", source: "discovery",
    lead_score: 42, updated_at: null, created_at: null, google_maps_url: null, address: "Tunis",
    rating: 4.5, review_count: 12, country: "Tunisia", industry: "Logistics", business_type: "SaaS",
    email: "hi@acme.tn", phone: "+21622", seo_score: 61, status_notes: null, hours: null,
    description: null, price_level: null, facebook: null, instagram: null, linkedin: null,
    twitter: null, tags: null,
    research,
    events: [],
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/leads/l1"]}>
        <Routes>
          <Route path="/leads/:id" element={<LeadsDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("LeadsDetail", () => {
  it("renders the research summary and sources", async () => {
    renderDetail();
    expect(await screen.findByText(/Research/i)).toBeInTheDocument();
    expect(screen.getByText(/Acme is a logistics SaaS/i)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "Acme site" });
    expect(link).toHaveAttribute("href", "https://acme.tn");
  });

  it("highlights hunted fields in cyan and shows the legend", async () => {
    renderDetail({
      summary: "s", status: "ok", sources: [],
      hunted_fields: ["email", "phone"],
    });
    expect(await screen.findByText("hi@acme.tn")).toBeInTheDocument();
    expect(screen.getByText("hi@acme.tn").closest("td")).toHaveClass("hunted");
    expect(screen.getByText("+21622").closest("td")).toHaveClass("hunted");
    expect(screen.getByText(/Cyan values were found by Start hunting/i)).toBeInTheDocument();
  });
});
