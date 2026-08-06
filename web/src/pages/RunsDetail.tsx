import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { fetchRun } from "../api/runs";
import { StatusBadge } from "../components/StatusBadge";

export default function RunsDetail() {
  const { id = "" } = useParams();
  const { data: run } = useQuery({
    queryKey: ["run", id],
    queryFn: () => fetchRun(id),
  });

  if (!run) return <p className="muted">Loading…</p>;

  return (
    <div>
      <h2>{run.agent_name} <StatusBadge status={run.status} /></h2>
      <p className="muted">Pipeline: {run.pipeline_run_id} · Model: {run.model ?? "—"}</p>

      <div className="panel">
        <h3>Input</h3>
        <pre>{run.input_summary ?? "—"}</pre>
      </div>

      <div className="panel">
        <h3>Output summary</h3>
        <pre>{run.output_summary ?? "—"}</pre>
      </div>

      {run.output_json ? (
        <div className="panel">
          <h3>Output JSON</h3>
          <pre>{JSON.stringify(run.output_json, null, 2)}</pre>
        </div>
      ) : null}

      {run.apis_consumed?.length ? (
        <div className="panel">
          <h3>APIs consumed</h3>
          <pre>{JSON.stringify(run.apis_consumed, null, 2)}</pre>
        </div>
      ) : null}

      {run.error_message ? (
        <div className="panel">
          <h3>Error</h3>
          <pre>{run.error_message}</pre>
        </div>
      ) : null}

      <p><Link to="/runs">← Back to runs</Link></p>
    </div>
  );
}
