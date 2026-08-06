import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { fetchLeads } from "../api/leads";
import { StatusBadge } from "../components/StatusBadge";

const STATUSES = ["raw", "categorized", "enriched", "contacted", "converted", "unreachable", "low_priority"];

export default function Leads() {
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const { data: leads } = useQuery({
    queryKey: ["leads", status],
    queryFn: () => fetchLeads(status || undefined),
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

      {!leads?.length ? (
        <p className="muted">No leads yet. Run the discovery pipeline.</p>
      ) : (
        <table className="data">
          <thead>
            <tr>
              <th>Name</th>
              <th>URL</th>
              <th>Status</th>
              <th>Source</th>
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
                <td>{lead.lead_score ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
