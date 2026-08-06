import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { fetchLead, updateLead } from "../api/leads";
import { StatusBadge } from "../components/StatusBadge";

const STATUSES = ["raw", "categorized", "enriched", "contacted", "converted", "unreachable", "low_priority"];

export default function LeadsDetail() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const [flash, setFlash] = useState<string | null>(null);

  const { data: lead } = useQuery({
    queryKey: ["lead", id],
    queryFn: () => fetchLead(id),
  });

  const save = useMutation({
    mutationFn: (status: string) => updateLead(id, { status }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lead", id] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      setFlash("Status updated.");
    },
    onError: (e: Error) => setFlash(e.message),
  });

  if (!lead) return <p className="muted">Loading…</p>;

  const rows: Array<[string, string]> = [
    ["Source", lead.source ?? "—"],
    ["Country", lead.country ?? "—"],
    ["Industry", lead.industry ?? "—"],
    ["Business type", lead.business_type ?? "—"],
    ["Email", lead.email ?? "—"],
    ["Phone", lead.phone ?? "—"],
    ["SEO score", lead.seo_score != null ? String(lead.seo_score) : "—"],
    ["Lead score", lead.lead_score != null ? String(lead.lead_score) : "—"],
  ];

  return (
    <div>
      {flash ? <div className="flash">{flash}</div> : null}
      <h2>{lead.name ?? "—"} <StatusBadge status={lead.status} /></h2>
      {lead.url ? <p className="muted"><a href={lead.url} target="_blank" rel="noopener noreferrer">{lead.url}</a></p> : null}

      <div className="panel">
        <table className="data">
          <tbody>
            {rows.map(([k, v]) => (
              <tr key={k}><th style={{ width: 140 }}>{k}</th><td>{v}</td></tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <h3>Update status</h3>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const fd = new FormData(e.currentTarget);
            save.mutate(String(fd.get("status")));
          }}
        >
          <div className="form-row" style={{ maxWidth: 240 }}>
            <label htmlFor="status">Status</label>
            <select id="status" name="status" defaultValue={lead.status ?? "raw"}>
              {STATUSES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          <button className="btn" type="submit" disabled={save.isPending}>Save</button>
        </form>
      </div>

      <div className="panel">
        <h3>Events</h3>
        {!lead.events?.length ? (
          <p className="muted">No events.</p>
        ) : (
          <table className="data">
            <thead>
              <tr><th>Type</th><th>Agent run</th><th>When</th></tr>
            </thead>
            <tbody>
              {lead.events.map((e) => (
                <tr key={e.id}>
                  <td><StatusBadge status={e.event_type} /></td>
                  <td className="muted">{e.agent_run_id ?? "—"}</td>
                  <td className="muted">{e.created_at ? new Date(e.created_at).toLocaleString() : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <p><Link to="/leads">← Back to leads</Link></p>
    </div>
  );
}
