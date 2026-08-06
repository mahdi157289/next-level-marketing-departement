import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchRuns } from "../api/runs";
import { StatusBadge } from "../components/StatusBadge";

function durationMs(row: { started_at: string | null; finished_at: string | null }): string {
  if (!row.started_at || !row.finished_at) return "—";
  const d = new Date(row.finished_at).getTime() - new Date(row.started_at).getTime();
  if (d < 1000) return `${Math.round(d)} ms`;
  return `${(d / 1000).toFixed(2)} s`;
}

export default function Runs() {
  const { data: runs } = useQuery({ queryKey: ["runs"], queryFn: fetchRuns });

  if (!runs?.length) return <p className="muted">No agent runs yet.</p>;

  return (
    <table className="data">
      <thead>
        <tr>
          <th>Agent</th>
          <th>Model</th>
          <th>Status</th>
          <th>Duration</th>
          <th>Records</th>
          <th>Started</th>
        </tr>
      </thead>
      <tbody>
        {runs.map((r) => (
          <tr key={r.id}>
            <td><Link to={`/runs/${r.id}`}>{r.agent_name}</Link></td>
            <td className="muted">{r.model ?? "—"}</td>
            <td><StatusBadge status={r.status} /></td>
            <td>{durationMs(r)}</td>
            <td>{r.records_processed ?? 0}</td>
            <td className="muted">{r.started_at ? new Date(r.started_at).toLocaleString() : "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
