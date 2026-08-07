import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchSkillHealth, fetchToolCatalog } from "../api/agents";
import type { SkillHealthResponse } from "../api/types";
import type { ToolCatalogItem } from "../api/agents";

type LampStatus = "ok" | "fail" | "skip" | "idle";

const LAMP_LABEL: Record<LampStatus, string> = {
  ok: "Works",
  fail: "Broken",
  skip: "Not configured / skipped",
  idle: "Not checked yet",
};

export function Lamp({ status, detail }: { status: LampStatus; detail?: string }) {
  return (
    <span
      className={`lamp ${status}`}
      role="img"
      aria-label={LAMP_LABEL[status]}
      title={`${LAMP_LABEL[status]}${detail ? ` — ${detail}` : ""}`}
    />
  );
}

export default function Tools() {
  const { data: tools } = useQuery<ToolCatalogItem[]>({
    queryKey: ["tools"],
    queryFn: fetchToolCatalog,
  });

  const health = useQuery<SkillHealthResponse>({
    queryKey: ["tools-health"],
    queryFn: fetchSkillHealth,
    retry: false,
  });

  const bySkill = new Map(
    (health.data?.results ?? []).map((r) => [r.skill_id, r]),
  );
  const checking = health.isLoading || health.isFetching;

  if (!tools?.length) return <p className="muted">No tools registered.</p>;

  return (
    <div>
      <h2>Tools / APIs / MCPs catalog</h2>
      <p className="muted">
        <Link to="/agents">← Agents</Link>
      </p>
      <p className="muted">
        Live skill checks run automatically on load.{" "}
        <button className="btn" style={{ fontSize: 12, padding: "0.25rem 0.6rem" }} onClick={() => health.refetch()} disabled={checking}>
          {checking ? "Checking…" : "Re-run checks"}
        </button>
      </p>
      <p className="muted" style={{ display: "flex", gap: "1rem", marginTop: "0.5rem" }}>
        <span>
          <Lamp status="ok" /> works
        </span>
        <span>
          <Lamp status="fail" /> broken
        </span>
        <span>
          <Lamp status="skip" /> not configured
        </span>
        <span>
          <Lamp status="idle" /> not run
        </span>
      </p>
      <table className="data">
        <thead>
          <tr>
            <th>Tool</th>
            <th>Label</th>
            <th>Agents</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {tools.map((t) => {
            const r = bySkill.get(t.id);
            const status: LampStatus = r?.status ?? (health.error ? "idle" : "idle");
            return (
              <tr key={t.id}>
                <td>
                  <code>{t.id}</code>
                </td>
                <td>{t.label}</td>
                <td>{t.agents.join(", ") || "—"}</td>
                <td>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }}>
                    <Lamp status={status} detail={r?.detail} />
                    <span className="muted" style={{ fontSize: 12 }}>
                      {r ? `${LAMP_LABEL[status]} · ${r.latency_ms}ms` : "…"}
                    </span>
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {health.error ? <p className="muted">Health check failed: {String(health.error)}</p> : null}
    </div>
  );
}
