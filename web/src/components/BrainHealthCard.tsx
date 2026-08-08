import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { flushBrainCache, fetchBrainMetrics, fetchBrainStatus, fetchWorkerStatus } from "../api/brain";
import type { BrainMetric } from "../api/types";
import { Lamp } from "../pages/Tools";

function hitLabel(m: BrainMetric): string {
  if (m.graph_hits > 0) return `graph×${m.graph_hits}`;
  if (m.vector_hits > 0) return `vector×${m.vector_hits}`;
  if (m.cache_hit) return "cache";
  return "—";
}

function tookClass(m: BrainMetric): string {
  if (m.latency_ms == null) return "";
  return m.latency_ms < 200 ? "text-green" : "text-amber";
}

export default function BrainHealthCard() {
  const brain = useQuery({
    queryKey: ["brain-status"],
    queryFn: fetchBrainStatus,
    refetchInterval: 8000,
    retry: false,
  });
  const metrics = useQuery({
    queryKey: ["brain-metrics"],
    queryFn: () => fetchBrainMetrics(10),
    refetchInterval: 8000,
    retry: false,
  });
  const worker = useQuery({
    queryKey: ["worker-status"],
    queryFn: fetchWorkerStatus,
    refetchInterval: 8000,
    retry: false,
  });
  const qc = useQueryClient();
  const flush = useMutation({
    mutationFn: flushBrainCache,
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["brain-metrics"] });
      setFlushMsg(`Flushed ${res.flushed} cached key${res.flushed === 1 ? "" : "s"}.`);
    },
    onError: () => {
      setFlushMsg("Failed to flush cache.");
    },
  });
  const [flushMsg, setFlushMsg] = useState<string | null>(null);

  const rows = metrics.data?.metrics ?? [];
  const total = rows.length;
  const cacheHits = rows.filter((r) => r.cache_hit).length;
  const cachePct = total ? Math.round((cacheHits / total) * 100) : null;
  const avgLatency = total
    ? Math.round(rows.reduce((a, r) => a + (r.latency_ms ?? 0), 0) / total)
    : null;

  return (
    <div className="panel">
      <h2>Brain health</h2>
      <p className="lamp-row">
        <span>
          <Lamp status={brain.data?.available ? "ok" : "fail"} detail="graph" /> Graph
        </span>
        <span>
          <Lamp status={metrics.isError ? "fail" : "ok"} detail="rag" /> RAG
        </span>
        <span>
          <Lamp status={metrics.isError ? "fail" : "ok"} detail="cache" /> Cache
        </span>
      </p>
      <p className="muted">
        Cache hit: {cachePct == null ? "—" : `${cachePct}%`} · Avg latency:{" "}
        {avgLatency == null ? "—" : `${avgLatency}ms`} · Workers:{" "}
        {worker.data ? `${worker.data.active}/${worker.data.max_workers}` : "—"} · Queued:{" "}
        {worker.data?.queued ?? "—"}
      </p>
      <p>
        <button className="btn secondary" onClick={() => flush.mutate()} disabled={flush.isPending}>
          {flush.isPending ? "Flushing…" : "Flush cache"}
        </button>{" "}
        {flushMsg ? <span className="muted">{flushMsg}</span> : null}
      </p>
      {!rows.length ? (
        <p className="muted">No brain activity yet.</p>
      ) : (
        <table className="data">
          <thead>
            <tr>
              <th>Agent</th>
              <th>Asked for</th>
              <th>Hit</th>
              <th>Started</th>
              <th>Took</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((m) => (
              <tr key={m.id}>
                <td>{m.agent_name}</td>
                <td className="muted">{m.query ?? "—"}</td>
                <td>{hitLabel(m)}</td>
                <td className="muted">
                  {m.created_at ? new Date(m.created_at).toLocaleString() : "—"}
                </td>
                <td className={tookClass(m)}>{m.latency_ms == null ? "—" : `${m.latency_ms}ms`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
