import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { enrichLeads, fetchLeads } from "../api/leads";
import { StatusBadge } from "../components/StatusBadge";

const STATUSES = ["raw", "categorized", "enriched", "contacted", "converted", "unreachable", "low_priority"];

export default function Leads() {
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const [enrichMsg, setEnrichMsg] = useState<string | null>(null);
  const { data: leads } = useQuery({
    queryKey: ["leads", status],
    queryFn: () => fetchLeads(status || undefined),
  });

  const enrich = useMutation({
    mutationFn: () => enrichLeads(),
    onSuccess: (out) => setEnrichMsg(`Enrich started: ${out.target_count} leads (run ${out.pipeline_run_id.slice(0, 8)}). Refetch in a minute.`),
    onError: (e: Error) => setEnrichMsg(`Enrich failed: ${e.message}`),
  });

  return (
    <div>
      <div className="form-row" style={{ maxWidth: 240 }}>
        <label htmlFor="status-filter">Status</label>
        <select
          id="status-filter"
          value={status}
          onChange={(e) => {
            const v = e.target.value;
            setParams(v ? { status: v } : {});
          }}
        >
          <option value="">All</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>
      <div className="form-row" style={{ justifyContent: "space-between" }}>
        <span className="muted">Click Enrich to run the Lead Completion Agent over the most recent leads and fill missing fields.</span>
        <button className="btn" type="button" onClick={() => enrich.mutate()} disabled={enrich.isPending}>
          {enrich.isPending ? "Enriching…" : "Enrich leads"}
        </button>
      </div>
      {enrichMsg ? <p className="flash info">{enrichMsg}</p> : null}

      {!leads?.length ? (
        <p className="muted">No leads yet. Run the discovery pipeline.</p>
      ) : (
        <div className="table-scroll">
          <table className="data">
            <thead>
              <tr>
                <th>Name</th>
                <th>URL</th>
                <th>Status</th>
                <th>Source</th>
                <th>Industry</th>
                <th>Business type</th>
                <th>Country</th>
                <th>Address</th>
                <th>Rating</th>
                <th>Phone</th>
                <th>Email</th>
                <th>SEO</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              {leads.map((lead) => (
                <tr key={lead.id}>
                  <td><Link to={`/leads/${lead.id}`}>{lead.name ?? "—"}</Link></td>
                  <td>{lead.url ? <a href={lead.url} target="_blank" rel="noopener noreferrer">{lead.url}</a> : "—"}</td>
                  <td><StatusBadge status={lead.status} /></td>
                  <td>{lead.source ?? "—"}</td>
                  <td>{lead.industry ?? "—"}</td>
                  <td>{lead.business_type ?? "—"}</td>
                  <td>{lead.country ?? "—"}</td>
                  <td>{lead.address ?? "—"}</td>
                  <td>{lead.rating ? `${lead.rating}${lead.review_count ? ` (${lead.review_count})` : ""}` : "—"}</td>
                  <td>{lead.phone ?? "—"}</td>
                  <td>{lead.email ? <a href={`mailto:${lead.email}`}>{lead.email}</a> : "—"}</td>
                  <td>{lead.seo_score ?? "—"}</td>
                  <td>{lead.lead_score ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
