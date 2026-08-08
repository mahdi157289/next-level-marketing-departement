import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchRecentMissions } from "../api/missions";
import { fetchStats } from "../api/stats";
import { KpiCard } from "../components/KpiCard";
import { StatusBadge } from "../components/StatusBadge";
import { ScoutActiveBadge } from "../components/ScoutActiveBadge";
import BrainHealthCard from "../components/BrainHealthCard";

function fmt(v: number | null | undefined): string {
  return v == null ? "—" : String(v);
}

export default function Dashboard() {
  const { data: stats } = useQuery({ queryKey: ["stats"], queryFn: fetchStats });
  const { data: missions } = useQuery({
    queryKey: ["recent-missions"],
    queryFn: fetchRecentMissions,
  });

  return (
    <div>
      <div className="kpi-grid">
        <KpiCard label="Leads" value={fmt(stats?.leads_total)} />
        <KpiCard label="Avg score" value={fmt(stats?.leads_avg_score)} accent="cyan" />
        <KpiCard label="Runs today" value={fmt(stats?.runs_today)} />
        <KpiCard label="Success rate" value={stats?.run_success_rate != null ? `${stats.run_success_rate}%` : "—"} accent="cyan" />
      </div>

      <BrainHealthCard />

      <div className="panel">
        <h2>Active Scout</h2>
        <p>
          <ScoutActiveBadge active={Boolean(stats?.scout_active)} />
          {stats?.scout_active && stats.scout_last_seed ? (
            <span className="muted"> — running: {stats.scout_last_seed}</span>
          ) : null}
        </p>
        <Link className="btn" to="/scout-hq">Open Scout HQ</Link>
      </div>

      <div className="panel">
        <h2>Recent missions</h2>
        {!missions?.length ? (
          <p className="muted">No missions yet.</p>
        ) : (
          <table className="data">
            <thead>
              <tr>
                <th>Seed</th>
                <th>Status</th>
                <th>Trigger</th>
                <th>Started</th>
              </tr>
            </thead>
            <tbody>
              {missions.map((m) => (
                <tr key={m.id}>
                  <td>{m.seed_query ?? "—"}</td>
                  <td><StatusBadge status={m.status} /></td>
                  <td>{m.trigger ?? "—"}</td>
                  <td className="muted">{m.started_at ? new Date(m.started_at).toLocaleString() : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
